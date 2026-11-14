import React from 'react';
interface RichMessageTextProps {
  text: string;
  isUser?: boolean;
}
function renderInlineTokens(line: string, isUser: boolean): React.ReactNode[] {
  // Pisahkan berdasarkan **bold**, *italic*, dan `code`
  const tokenRegex = /(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/g;
  const parts = line.split(tokenRegex);
  return parts.map((part, idx) => {
    if (!part) return null;
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return (
        <strong
          key={idx}
          className={isUser ? 'font-bold text-white' : 'font-semibold text-[#27211e]'}
        >
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return (
        <em key={idx} className="italic">
          {part.slice(1, -1)}
        </em>
      );
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code
          key={idx}
          className={
            isUser
              ? 'px-1.5 py-0.5 rounded bg-white/20 font-mono text-[12px]'
              : 'px-1.5 py-0.5 rounded-md bg-[#fbf5f0] border border-[#eadfd7] font-mono text-[12px] text-[#b85328]'
          }
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    // Bersihkan sisa simbol markdown yang tidak berpasangan
    const cleaned = part.replace(/\*\*/g, '').replace(/`/g, '');
    return <React.Fragment key={idx}>{cleaned}</React.Fragment>;
  });
}
export const RichMessageText: React.FC<RichMessageTextProps> = ({ text, isUser = false }) => {
  const lines = String(text || '').split('\n');
  return (
    <div className="space-y-1.5 leading-relaxed">
      {lines.map((rawLine, lineIdx) => {
        const trimmed = rawLine.trim();
        if (!trimmed) {
          return <div key={lineIdx} className="h-1.5" />;
        }
        // Bullet point (- item atau * item)
        const bulletMatch = trimmed.match(/^[-•*]\s+(.+)$/);
        if (bulletMatch) {
          return (
            <div key={lineIdx} className="flex items-start gap-2 pl-1">
              <span
                className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${
                  isUser ? 'bg-white/80' : 'bg-[#d76b3e]'
                }`}
              />
              <div className="flex-1">{renderInlineTokens(bulletMatch[1], isUser)}</div>
            </div>
          );
        }
        // Numbered list (1. item)
        const numMatch = trimmed.match(/^(\d+\.)\s+(.+)$/);
        if (numMatch) {
          return (
            <div key={lineIdx} className="flex items-start gap-2 pl-1">
              <span
                className={`font-semibold text-xs mt-0.5 shrink-0 ${
                  isUser ? 'text-white/90' : 'text-[#d76b3e]'
                }`}
              >
                {numMatch[1]}
              </span>
              <div className="flex-1">{renderInlineTokens(numMatch[2], isUser)}</div>
            </div>
          );
        }
        return <p key={lineIdx}>{renderInlineTokens(rawLine, isUser)}</p>;
      })}
    </div>
  );
};
export default RichMessageText;
