"""Workflow LangGraph des 6 agents : preuves -> (événements ‖ portefeuille ‖ complotiste) -> avocat du diable -> [réponses] -> gouvernance -> synthèse."""
from __future__ import annotations

import contextvars
import json
import logging
import operator
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Callable

from langgraph.graph import END, START, StateGraph

from alphaforge.contracts import AnalysisRequest, FinalReport, GraphState, TokenUsage
from alphaforge.llm import LLMError, LLMRequest
from alphaforge.observability import bind_request_id
from alphaforge.retrieval import KnowledgeBase
from alphaforge.team.base import PROMPT_VERSION, AgentOutput, Evidence, Rebuttal, TeamAgent, brief, to_result
from alphaforge.team.conspiracy import ConspiracyOutput, ConspiracyTheorist
from alphaforge.team.devil import TARGETS, DevilOutput, DevilsAdvocate
from alphaforge.team.events import EventHunter, EventsOutput
from alphaforge.team.governance import GovernanceAgent, GovernanceOutput
from alphaforge.team.interfaces import MarketData, PortfolioProvider, ProfileChecks, QuantMetrics
from alphaforge.team.portfolio import PortfolioOutput, PortfolioStoryteller
from alphaforge.team.research import ResearchAgent, ResearchOutput
from alphaforge.tracing import span

logger = logging.getLogger("alphaforge.team")
# Abonné aux événements de progression de l'analyse en cours (ex. flux SSE du front) ; propagé aux threads comme le request_id.
_on_event: contextvars.ContextVar[Callable[[dict], None] | None] = contextvars.ContextVar("on_event", default=None)
ORDER = ("research", "event_hunter", "portfolio_storyteller", "conspiracy_theorist", "devils_advocate", "governance")
SECTIONS = (
    "1. Que s'est-il passé ?",
    "2. Pourquoi cela a-t-il pu arriver ?",
    "3. Qu'est-ce que cela signifie pour votre portefeuille ?",
    "4. Le débat",
    "5. Le verdict",
    "6. Sources et limites",
)
SYNTHESIS_SYSTEM = (
    "Tu rédiges la réponse finale d'un assistant d'analyse financière pour un investisseur non expert, en français clair, "
    "uniquement à partir du rapport validé fourni (ne rien ajouter). Utilise exactement ces sections en Markdown : "
    + " ; ".join(f"## {s}" for s in SECTIONS)
    + ". Sépare faits vérifiés, interprétations et scénarios hypothétiques. Cite les preuves entre crochets [E1]. "
    "Section 3, courte (8 lignes au plus), sans sous-titre : une phrase en **gras** qui dit simplement ce que cela change "
    "pour l'investisseur ; puis des puces '- ' commençant par **Ce que vous détenez :** (lignes concernées et leur poids), "
    "**Ce qui peut amortir ou amplifier :** (autres lignes du portefeuille), **Contrôles de votre profil :** (seulement les "
    "contrôles « attention » ou « non respecté », cités [E..], en disant clairement si la demande est incohérente avec le profil, "
    "sans acquiescer) et **À retenir :** (une notion financière expliquée en une phrase avec son cas). "
    "Pas de calcul ni de chiffre absent du rapport. "
    "Section 4 : interprétation initiale, meilleurs contre-arguments, ce qui a survécu et ce qui reste incertain ; "
    "résume brièvement les théories de l'agent complotiste en les présentant clairement comme non prouvées, avec l'avis de la gouvernance. "
    "Section 5 : ce que les preuves permettent de conclure et ce qui ne peut pas l'être ; respecte final_assessment ; "
    "n'écris AUCUNE recommandation d'achat ou de vente. N'invente aucun chiffre, aucune source, aucune date."
)
GENERAL_SYSTEM = (
    "Tu es l'assistant d'AlphaForge, une application pédagogique d'investissement. Aucune donnée de marché ni document "
    "n'est disponible : réponds avec tes connaissances générales, à n'importe quelle question, pour un débutant. "
    "FORMAT STRICT, 10 lignes maximum au total : "
    "1) une phrase de réponse directe, la plus importante, en **gras** ; "
    "2) puis 3 à 4 puces courtes ('- '), une idée par puce, une seule phrase chacune ; "
    "3) si un portefeuille est fourni et que c'est pertinent, une dernière ligne qui commence par 'Pour vous : '. "
    "Pas de titre, pas de tableau, pas de conclusion ni d'avertissement final (l'application l'affiche déjà). "
    "Mots simples, phrases courtes ; explique tout terme technique en quelques mots. "
    "Pour un fait récent (cours, actualité), dis en une demi-phrase que tu ne peux pas le confirmer, sans t'étendre. "
    "N'invente aucune source ni aucun chiffre récent ; n'écris AUCUNE recommandation d'achat ou de vente."
)


class TeamState(GraphState, total=False):
    evidence: list[Evidence]
    research: ResearchOutput
    events: EventsOutput
    portfolio: PortfolioOutput
    conspiracy: ConspiracyOutput
    devil: DevilOutput
    rebuttals: Annotated[list[Rebuttal], operator.add]
    debate_rounds: int
    governance: GovernanceOutput


class TeamReport(FinalReport):
    """FinalReport (compatible avec l'évaluation) + le détail structuré de l'analyse."""

    assessment: str
    debate_rounds: int
    evidence: list[Evidence]
    research: ResearchOutput
    events: EventsOutput
    portfolio: PortfolioOutput
    conspiracy: ConspiracyOutput = ConspiracyOutput(status="skipped")
    devil: DevilOutput
    rebuttals: list[Rebuttal]
    governance: GovernanceOutput
    failures: list[str]
    answer_mode: str = "evidence"  # evidence (5 agents) | general_knowledge (aucune preuve : LLM seul) | incomplete


class TeamOrchestrator:
    """Même interface que `Orchestrator` (`run(request) -> FinalReport`), avec 6 agents et un débat borné à 2 tours."""

    def __init__(
        self,
        llm,
        kb: KnowledgeBase | None = None,
        market: MarketData | None = None,
        quant: QuantMetrics | None = None,
        portfolios: PortfolioProvider | None = None,
        checker: ProfileChecks | None = None,
    ):
        self._llm, self._portfolios = llm, portfolios
        # collecte unique : actualités, prix, métriques de risque et contrôles du profil
        self._research = ResearchAgent(llm, kb, market, quant, checker)
        self._events, self._portfolio = EventHunter(llm), PortfolioStoryteller(llm)
        self._devil, self._governance = DevilsAdvocate(llm), GovernanceAgent(llm)
        self._conspiracy = ConspiracyTheorist(llm)
        self._debaters: dict[str, TeamAgent] = {
            "research": self._research, "event_hunter": self._events, "portfolio_storyteller": self._portfolio
        }

        graph = StateGraph(TeamState)
        graph.add_node("research", self._step(self._research, "research", self._run_research, lambda o: {"evidence": o.evidence}))
        graph.add_node("event_hunter", self._step(self._events, "events", lambda s: self._events.run(s["request"].question, s["evidence"])))
        graph.add_node("portfolio_storyteller", self._step(self._portfolio, "portfolio", lambda s: self._portfolio.run(s["request"], s["evidence"])))
        graph.add_node(
            "conspiracy_theorist",
            self._step(self._conspiracy, "conspiracy", lambda s: self._conspiracy.run(s["request"].question, s["evidence"])),
        )
        graph.add_node(
            "devils_advocate",
            self._step(self._devil, "devil", self._run_devil, lambda o: {"debate_rounds": 0 if o.status == "skipped" else 1}),
        )
        graph.add_node("respond", self._respond)
        graph.add_node("governance", self._step(self._governance, "governance", self._run_governance))
        graph.add_node("synthesize", self._observed("synthesis", self._synthesize, lambda update: update["report"].answer))

        graph.add_edge(START, "research")
        # Sans preuve, inutile de chercher des événements ou de débattre : on passe directement à la gouvernance.
        graph.add_conditional_edges(
            "research",
            lambda s: ["event_hunter", "portfolio_storyteller", "conspiracy_theorist"] if s["evidence"] else "governance",
            ["event_hunter", "portfolio_storyteller", "conspiracy_theorist", "governance"],
        )
        # indépendants entre eux (ils ne lisent que les preuves), puis jonction
        graph.add_edge(["event_hunter", "portfolio_storyteller", "conspiracy_theorist"], "devils_advocate")
        # Tour 2 seulement s'il existe une objection sérieuse (haute ou moyenne) adressée à un agent.
        graph.add_conditional_edges(
            "devils_advocate",
            lambda s: "respond" if self._objections(s) else "governance",
            ["respond", "governance"],
        )
        graph.add_edge("respond", "governance")
        graph.add_edge("governance", "synthesize")
        graph.add_edge("synthesize", END)
        self._graph = graph.compile()

    # --- Noeuds --------------------------------------------------------------------------------------------------
    def _step(self, agent: TeamAgent, key: str, run: Callable, extra: Callable[[AgentOutput], dict] | None = None):
        """Exécute un agent : un échec LLM devient une sortie `failed` visible (jamais une sortie inventée)."""

        def node(state: TeamState) -> dict:
            started = time.perf_counter()
            try:
                output, responses = run(state)
            except LLMError as exc:
                logger.error("agent_error", extra={"event": "agent_error", "agent": agent.name, "error_type": type(exc).__name__})
                output, responses = agent.failed(type(exc).__name__), []
            result = to_result(agent.name, output, responses, getattr(output, "sources", None))
            logger.info(
                "agent_end",
                extra={
                    "event": "agent_end", "agent": agent.name, "status": output.status, "debate_round": max(1, state.get("debate_rounds", 0)),
                    "prompt_version": PROMPT_VERSION, "model_id": result.model_id, "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens, "estimated_cost_usd": result.estimated_cost_usd,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "evidence_ids": sorted(set(re.findall(r"\bE\d+\b", output.model_dump_json()))),
                },
            )
            return {key: output, "agent_results": [result], **(extra(output) if extra else {})}

        return self._observed(agent.name, node, lambda update: update[key].model_dump(mode="json"), lambda update: update[key].status)

    @staticmethod
    def _observed(name: str, fn: Callable, outputs: Callable, status: Callable = lambda _: "ok") -> Callable:
        """Enveloppe une étape : span MLflow (si le tracing est actif) et événements agent_start / agent_end pour le front."""

        def emit(**event) -> None:
            callback = _on_event.get()
            if callback:
                callback({"agent": name, **event})

        def wrapper(*args):
            emit(type="agent_start")
            try:
                with span(name, "AGENT") as current:
                    result = fn(*args)
                    current.outputs(outputs(result))
            except Exception:
                emit(type="agent_end", status="failed")
                raise
            emit(type="agent_end", status=status(result))
            return result

        return wrapper

    def _run_research(self, state: TeamState):
        return self._research.run(state["request"])

    def _run_devil(self, state: TeamState):
        return self._devil.run(state["request"].question, state["evidence"], state["research"], state["events"], state["portfolio"])

    def _run_governance(self, state: TeamState):
        events, portfolio, devil = state.get("events"), state.get("portfolio"), state.get("devil")
        statuses = {"research": state["research"].status}
        statuses.update({n: o.status for n, o in (("event_hunter", events), ("portfolio_storyteller", portfolio), ("devils_advocate", devil)) if o})
        # Le complotiste n'est pas dans `statuses` : son échec (visible dans `failures`) ne plafonne pas le verdict.
        return self._governance.run(
            state["request"],
            state.get("evidence", []),
            state["research"],
            events or EventsOutput(status="skipped"),
            portfolio or PortfolioOutput(status="skipped"),
            devil or DevilOutput(status="skipped"),
            state.get("rebuttals", []),
            statuses,
            state.get("conspiracy"),
        )

    @staticmethod
    def _objections(state: TeamState) -> dict:
        """Objections sérieuses par agent, seulement pour les agents qui ont produit quelque chose à défendre."""
        outputs = {"research": state["research"], "event_hunter": state.get("events"), "portfolio_storyteller": state.get("portfolio")}
        found = {t: state["devil"].objections_for(t) for t in TARGETS if outputs[t] and outputs[t].status in ("ok", "partial")}
        return {t: o for t, o in found.items() if o}

    def _respond(self, state: TeamState) -> dict:
        """Tour 2 : seuls les agents objectés répondent, en parallèle, avec des preuves existantes."""
        evidence = state["evidence"]
        views = {
            "research": state["research"].model_dump(mode="json", include={"key_facts", "missing_information"}),
            "event_hunter": state["events"].model_dump(mode="json", include={"identified_events", "potential_market_mechanisms", "uncertainties"}),
            "portfolio_storyteller": state["portfolio"].model_dump(mode="json", include={"direct_exposure", "indirect_exposure", "potential_impacts", "limitations"}),
        }
        jobs = [(self._debaters[t], views[t], objections) for t, objections in self._objections(state).items()]

        def run(job):
            agent, view, objections = job
            started = time.perf_counter()
            try:
                rebuttals, response = agent.respond(view, objections, evidence)
                output, responses = AgentOutput(), [response]
            except LLMError as exc:
                logger.error("agent_error", extra={"event": "agent_error", "agent": agent.name, "error_type": type(exc).__name__})
                rebuttals = [
                    Rebuttal(agent=agent.name, objection=o.objection, response="(agent indisponible)", missing_evidence=f"Réponse impossible : {type(exc).__name__}")
                    for o in objections
                ]
                output, responses = agent.failed(type(exc).__name__), []
            result = to_result(f"{agent.name}:rebuttal", output, responses).model_copy(update={"summary": f"{len(rebuttals)} réponse(s)"})
            logger.info(
                "agent_end",
                extra={"event": "agent_end", "agent": result.agent, "status": output.status, "debate_round": 2, "prompt_version": PROMPT_VERSION,
                       "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                       "evidence_ids": sorted({i for r in rebuttals for i in r.evidence_ids})},
            )
            return rebuttals, result

        def traced_run(job):
            name = f"{job[0].name}:rebuttal"
            return self._observed(name, run, lambda out: [r.model_dump(mode="json") for r in out[0]], lambda out: "failed" if out[1].error else "ok")(job)

        with ThreadPoolExecutor(len(jobs)) as pool:  # le contexte (request_id, span MLflow) est propagé à chaque thread
            outcomes = list(pool.map(lambda j, ctx: ctx.run(traced_run, j), jobs, [contextvars.copy_context() for _ in jobs]))
        return {
            "rebuttals": [r for rebuttals, _ in outcomes for r in rebuttals],
            "agent_results": [result for _, result in outcomes],
            "debate_rounds": 2,
        }

    def _synthesize(self, state: TeamState) -> dict:
        request, evidence, gov = state["request"], state.get("evidence", []), state["governance"]
        events, portfolio, devil = state.get("events", EventsOutput()), state.get("portfolio", PortfolioOutput()), state.get("devil", DevilOutput())
        usage, cost, error = TokenUsage(), 0.0, None
        answer = None
        if evidence and gov.status != "failed":  # sinon réponse incomplète construite par le code, sans LLM
            payload = {
                **request.profile(),
                "rapport_gouvernance": gov.model_dump(mode="json", exclude={"schema_version", "facts", "interpretations", "hypothetical_scenarios"}),
                "preuves": [brief(e) for e in evidence],
                "chronologie": events.event_timeline,
                "lignes_du_portefeuille": [h.model_dump(mode="json") for h in request.portfolio.holdings] if request.portfolio else [],
                "portefeuille": portfolio.model_dump(
                    mode="json",
                    include={"personalized", "direct_exposure", "indirect_exposure", "quantitative_observations", "relevant_financial_concepts", "educational_explanation", "potential_impacts"},
                ),
                "debat": {
                    "contre_arguments": devil.counterarguments,
                    "objections": [c.model_dump() for c in devil.challenged_claims],
                    "reponses": [r.model_dump() for r in state.get("rebuttals", [])],
                    "theories_complotistes_non_prouvees": [r.model_dump() for r in gov.conspiracy_review],
                },
            }
            try:
                response = self._llm.complete(LLMRequest(task="orchestration", agent="synthesis", system=SYNTHESIS_SYSTEM, prompt=json.dumps(payload, ensure_ascii=False)))
                answer, usage, cost = response.text, response.usage, response.estimated_cost_usd
            except LLMError as exc:
                error = type(exc).__name__
                logger.error("agent_error", extra={"event": "agent_error", "agent": "synthesis", "error_type": error})
        mode = "evidence"
        if answer is None and not evidence:  # aucune donnée : le LLM répond avec ses connaissances générales
            answer, usage, cost, error = self._general_answer(request)
            mode = "general_knowledge" if answer else "incomplete"
        elif answer is None:
            mode = "incomplete"
        if answer is None:
            answer = self._static_answer(state)
        if mode != "general_knowledge":  # l'interface signale déjà le mode « connaissances générales » (answer_mode)
            answer = self._finalize(answer, evidence, gov)

        results = sorted(state["agent_results"], key=lambda r: (ORDER.index(r.agent) if r.agent in ORDER else len(ORDER), r.agent))
        costs = [r.estimated_cost_usd for r in results] + [cost]
        cited_ids = {i for c in gov.validated_claims for i in c.evidence_ids} or {e.id for e in evidence}
        failures = [r.agent for r in results if r.error] + (["synthesis"] if error else [])
        return {
            "report": TeamReport(
                request_id=request.request_id,
                persona=request.persona,
                answer=answer,
                sources=sorted({e.source for e in evidence if e.id in cited_ids}),
                agent_results=results,
                usage=sum((r.usage for r in results), TokenUsage()) + usage,
                estimated_cost_usd=None if None in costs else sum(costs),
                assessment=gov.final_assessment,
                debate_rounds=state.get("debate_rounds", 0),
                evidence=evidence,
                research=state["research"],
                events=events,
                portfolio=portfolio,
                conspiracy=state.get("conspiracy", ConspiracyOutput(status="skipped")),
                devil=devil,
                rebuttals=state.get("rebuttals", []),
                governance=gov,
                failures=failures,
                answer_mode=mode,
            )
        }

    def _general_answer(self, request: AnalysisRequest) -> tuple[str | None, TokenUsage, float | None, str | None]:
        """Sans preuve : réponse libre du LLM (connaissances générales), clairement signalée comme non vérifiée."""
        payload = {
            "question": request.question,
            **request.profile(),
            "portefeuille": request.portfolio.model_dump(mode="json") if request.portfolio else None,
        }
        try:
            response = self._llm.complete(LLMRequest(task="orchestration", agent="general", system=GENERAL_SYSTEM, prompt=json.dumps(payload, ensure_ascii=False)))
        except LLMError as exc:
            logger.error("agent_error", extra={"event": "agent_error", "agent": "general", "error_type": type(exc).__name__})
            return None, TokenUsage(), 0.0, type(exc).__name__
        text = (response.text or "").strip()
        return (text or None), response.usage, response.estimated_cost_usd, None

    @staticmethod
    def _sources_block(evidence: list[Evidence], gov: GovernanceOutput) -> str:
        cited_ids = {i for c in gov.validated_claims for i in c.evidence_ids} or {e.id for e in evidence}
        lines = [f"- [{e.id}] {e.source} ({e.date or 'date inconnue'}) — {e.reference}" for e in evidence if e.id in cited_ids]
        lines += [f"- Limite : {x}" for x in [*gov.limitations, *gov.evidence_gaps]]
        return "\n".join(lines) or "- Aucune source disponible."

    def _finalize(self, answer: str, evidence: list[Evidence], gov: GovernanceOutput) -> str:
        """Garde-fous du texte final : pas de citation inconnue, section sources toujours présente."""
        known = {e.id for e in evidence}
        answer = re.sub(r"\[E\d+\]", lambda m: m.group(0) if m.group(0)[1:-1] in known else "[source inconnue retirée]", answer)
        if "Sources et limites" not in answer:
            answer += f"\n\n## {SECTIONS[5]}\n{self._sources_block(evidence, gov)}"
        return answer

    def _static_answer(self, state: TeamState) -> str:
        """Réponse incomplète sans LLM (aucune preuve, gouvernance en échec ou synthèse indisponible)."""
        evidence, gov = state.get("evidence", []), state["governance"]
        prices = [e for e in evidence if e.kind == "price"]
        portfolio = state.get("portfolio")
        body = [
            "Analyse incomplète : " + ("; ".join(gov.limitations) or "preuves insuffisantes."),
            "\n".join(f"- {e.claim} [{e.id}]" for e in prices) or "Aucun mouvement de prix vérifiable n'est disponible.",
            "Les données disponibles ne permettent pas d'expliquer ce mouvement.",
            (portfolio.educational_explanation or "Impact personnalisé indisponible.") if portfolio else "Impact personnalisé indisponible : portefeuille ou preuves manquants.",
            "Aucun débat n'a pu être mené faute de conclusions à contester.",
            f"Évaluation : {gov.final_assessment}. Aucune conclusion ne peut être tirée ; ceci n'est pas une recommandation d'achat ou de vente.",
            self._sources_block(evidence, gov),
        ]
        return "\n\n".join(f"## {title}\n{text}" for title, text in zip(SECTIONS, body))

    # --- Point d'entrée --------------------------------------------------------------------------------------------
    def run(self, request: AnalysisRequest, on_event: Callable[[dict], None] | None = None) -> TeamReport:
        """`on_event` reçoit {"type": "agent_start" | "agent_end", "agent": nom, "status": ...} au fil de l'analyse."""
        token = _on_event.set(on_event)
        try:
            return self._run(request)
        finally:
            _on_event.reset(token)

    def _run(self, request: AnalysisRequest) -> TeamReport:
        with bind_request_id(request.request_id):
            started = time.perf_counter()
            if request.portfolio is None and request.user_id and self._portfolios:
                try:
                    request = request.model_copy(update={"portfolio": self._portfolios.get(request.user_id)})
                except Exception as exc:  # interface externe : sans portefeuille, l'analyse devient générale
                    logger.warning("portfolio_error", extra={"event": "portfolio_error", "error_type": type(exc).__name__})
            inputs = {"question": request.question, "persona": request.persona.value, "tickers": request.tickers,
                      "holdings": [h.ticker for h in request.portfolio.holdings] if request.portfolio else []}
            with span("analyze", "CHAIN", inputs, request_id=request.request_id) as current:
                report = self._graph.invoke({"request": request, "agent_results": [], "rebuttals": [], "debate_rounds": 0})["report"]
                current.outputs(report.answer)
                current.attributes(
                    assessment=report.assessment, answer_mode=report.answer_mode, debate_rounds=report.debate_rounds,
                    input_tokens=report.usage.input_tokens, output_tokens=report.usage.output_tokens, failures=report.failures,
                )
            logger.info(
                "request_end",
                extra={
                    "event": "request_end", "workflow": "team", "prompt_version": PROMPT_VERSION,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "input_tokens": report.usage.input_tokens, "output_tokens": report.usage.output_tokens,
                    "estimated_cost_usd": report.estimated_cost_usd, "assessment": report.assessment,
                    "debate_rounds": report.debate_rounds, "evidence_count": len(report.evidence), "failures": report.failures,
                },
            )
            return report
