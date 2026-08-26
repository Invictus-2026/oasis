import { Component, type ReactNode } from "react";

/** One panel failing must never white-screen a live demo. */
export default class ErrorBoundary extends Component<
  { children: ReactNode; label: string },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error("[SpillTrace] panel crashed:", this.props.label, error);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded-lg border border-alert-500/30 bg-alert-500/5 px-3 py-2">
          <p className="text-[11px] text-alert-500">{this.props.label} unavailable</p>
          <p className="mt-0.5 text-[10px] text-ink-500">
            The rest of the pipeline is unaffected.
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}
