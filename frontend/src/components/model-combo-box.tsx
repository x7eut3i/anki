"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { ChevronDown } from "lucide-react";

interface ModelComboBoxProps {
  value: string;
  onChange: (value: string) => void;
  models: string[];
  placeholder?: string;
  className?: string;
  id?: string;
}

/**
 * Combo box for AI model selection: supports both dropdown picking and manual typing.
 */
export function ModelComboBox({
  value,
  onChange,
  models,
  placeholder = "输入或选择模型",
  className,
  id,
}: ModelComboBoxProps) {
  const [open, setOpen] = React.useState(false);
  const [filter, setFilter] = React.useState("");
  const containerRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Close on outside click
  React.useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = React.useMemo(() => {
    if (!filter) return models;
    const lower = filter.toLowerCase();
    return models.filter((m) => m.toLowerCase().includes(lower));
  }, [models, filter]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value;
    onChange(v);
    setFilter(v);
    if (!open && models.length > 0) setOpen(true);
  };

  const handleSelect = (m: string) => {
    onChange(m);
    setFilter("");
    setOpen(false);
    inputRef.current?.focus();
  };

  const toggleDropdown = () => {
    if (open) {
      setOpen(false);
    } else if (models.length > 0) {
      setFilter("");
      setOpen(true);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <div className="flex">
        <input
          ref={inputRef}
          id={id}
          type="text"
          value={value}
          onChange={handleInputChange}
          onFocus={() => { if (models.length > 0) setOpen(true); }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="flex h-10 w-full rounded-l-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          autoComplete="off"
        />
        <button
          type="button"
          onClick={toggleDropdown}
          tabIndex={-1}
          className="flex items-center justify-center h-10 w-9 rounded-r-md border border-l-0 border-input bg-muted hover:bg-accent text-muted-foreground transition-colors"
          aria-label="展开模型列表"
        >
          <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
        </button>
      </div>
      {open && filtered.length > 0 && (
        <ul
          className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md border border-input bg-background py-1 shadow-md"
          role="listbox"
        >
          {filtered.map((m) => (
            <li
              key={m}
              role="option"
              aria-selected={m === value}
              onClick={() => handleSelect(m)}
              className={cn(
                "cursor-pointer px-3 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground",
                m === value && "bg-accent/50 font-medium"
              )}
            >
              {m}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
