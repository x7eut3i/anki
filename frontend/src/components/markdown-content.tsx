"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownContentProps {
  content: string;
  className?: string;
}

export function MarkdownContent({ content, className = "" }: MarkdownContentProps) {
  return (
    <div className={`prose prose-sm dark:prose-invert max-w-none ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="text-lg font-bold mt-4 mb-2">{children}</h1>,
          h2: ({ children }) => <h2 className="text-base font-bold mt-3 mb-2">{children}</h2>,
          h3: ({ children }) => <h3 className="text-sm font-bold mt-2 mb-1">{children}</h3>,
          p: ({ children }) => <p className="text-sm text-muted-foreground leading-relaxed mb-2">{children}</p>,
          ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 text-sm text-muted-foreground">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 text-sm text-muted-foreground">{children}</ol>,
          li: ({ children }) => <li className="text-sm text-muted-foreground leading-relaxed">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-primary/30 pl-4 my-2 text-sm text-muted-foreground italic">
              {children}
            </blockquote>
          ),
          code: ({ children, className }) => {
            const isBlock = className?.includes("language-");
            if (isBlock) {
              return (
                <pre className="bg-muted rounded-md p-3 text-xs overflow-x-auto my-2">
                  <code>{children}</code>
                </pre>
              );
            }
            return <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono">{children}</code>;
          },
          table: ({ children }) => (
            <div className="overflow-x-auto my-2">
              <table className="w-full text-sm border-collapse">{children}</table>
            </div>
          ),
          th: ({ children }) => <th className="border-b-2 px-2 py-1 text-left font-semibold text-xs">{children}</th>,
          td: ({ children }) => <td className="border-b px-2 py-1 text-xs text-muted-foreground">{children}</td>,
          hr: () => <hr className="my-3 border-muted" />,
          a: ({ href, children }) => (
            <a href={href} className="text-primary underline hover:no-underline" target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
