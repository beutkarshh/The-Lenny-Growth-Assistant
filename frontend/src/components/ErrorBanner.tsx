interface Props {
  message: string;
  onDismiss: () => void;
}

// design.md §3: "Provider unavailable" and general failure states must be an
// inline banner explaining the specific failure — never a silent hang.
// §5: loading/error states announced via aria-live so screen reader users
// aren't left waiting silently.
export default function ErrorBanner({ message, onDismiss }: Props) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="flex items-start justify-between gap-3 border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800"
    >
      <span>⚠ {message}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss error"
        className="shrink-0 text-red-600 hover:text-red-900"
      >
        ✕
      </button>
    </div>
  );
}
