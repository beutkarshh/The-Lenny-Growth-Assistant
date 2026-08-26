import { useState } from "react";
import type { FormEvent } from "react";

interface Props {
  disabled: boolean;
  onSend: (content: string) => void;
}

export default function Composer({ disabled, onSend }: Props) {
  const [value, setValue] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 border-t border-slate-200 bg-white p-3">
      <label htmlFor="composer-input" className="sr-only">
        Message
      </label>
      <input
        id="composer-input"
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled}
        placeholder="Ask about growth or product strategy from Lenny's Podcast..."
        className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-50 disabled:text-slate-400"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        Send
      </button>
    </form>
  );
}
