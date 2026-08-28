import { useEffect, useRef } from "react";

export default function Terminal({ lines, side = false }) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (atBottom) el.scrollTop = el.scrollHeight;
  }, [lines]);

  return (
    <section className={"panel term-panel" + (side ? " term-side" : "")}>
      <div className="panel-title">
        TELEMETRY <span className="blink">▮</span>
      </div>
      <pre className="terminal" ref={ref}>
        {lines.map((l) => "» " + l).join("\n")}
      </pre>
    </section>
  );
}
