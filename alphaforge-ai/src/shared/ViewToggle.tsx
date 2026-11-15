import { useAppStore } from './store';
import { SegmentedToggle } from './ui';
import type { ViewMode } from '../data/types';

/** Global Guided / Advanced switch. Changes what is shown, never the underlying numbers. */
export function ViewToggle() {
  const viewMode = useAppStore((s) => s.viewMode);
  const setViewMode = useAppStore((s) => s.setViewMode);
  return (
    <div className="flex items-center gap-2">
      <SegmentedToggle<ViewMode>
        label="Reading level"
        value={viewMode}
        onChange={setViewMode}
        options={[
          { value: 'guided', label: 'Guided' },
          { value: 'advanced', label: 'Advanced' },
        ]}
      />
      <span className="sr-only">Guided explains in plain language. Advanced adds numbers such as volatility.</span>
    </div>
  );
}
