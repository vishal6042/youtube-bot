import { useRef, useState } from "react";
import { Btn, Empty, Pager, fmtWhen, usePaged } from "../../ui.jsx";

const hasValue = (s) => s && s !== "—";

function ImageRow({ img, busy, onUpload }) {
  const inputRef = useRef(null);
  const [bust, setBust] = useState(0);   // forces the preview to reload after a replace

  const pick = (e) => {
    const file = e.target.files?.[0];
    if (file) onUpload(img.name, file, () => setBust(Date.now()));
    e.target.value = "";
  };

  return (
    <tr>
      <td><img className="brand-img" src={`/api/brand/${img.name}?t=${bust}`} alt="" loading="lazy" /></td>
      <td>
        <div className="t">{img.role}</div>
        <div className="k" style={{ overflowWrap: "anywhere" }}>{img.name}</div>
      </td>
      <td className="num">{img.dimensions || <span className="faint">unknown</span>}</td>
      <td className="r num muted">{img.size_kb} KB</td>
      <td className="num muted">{hasValue(img.recommended) ? img.recommended : <span className="faint">any size</span>}</td>
      <td className="muted">{fmtWhen(img.modified, { time: false })}</td>
      <td className="r">
        <Btn size="sm" icon="upload" disabled={busy} aria-label={`Replace ${img.name}`}
             onClick={() => inputRef.current?.click()}>
          Replace
        </Btn>
        <input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp" hidden
               aria-label={`New file for ${img.name}`} onChange={pick} />
      </td>
    </tr>
  );
}

export default function BrandTab({ images, docs, busy, onUpload }) {
  const paged = usePaged(images, 10);

  return (
    <section className="card" style={{ padding: "8px 8px 16px" }} aria-label="Brand images">
      <div className="rowf" style={{ padding: "12px 12px 6px" }}>
        <h2>Brand images</h2>
        <span className="muted" style={{ fontSize: 13 }}>Replacing an image keeps a backup of the old one.</span>
      </div>

      {images.length === 0 ? (
        <Empty icon="folder" title="No brand images yet">
          Put png, jpg or webp files in the brand folder and they show up here.
        </Empty>
      ) : (
        <>
          <div className="scroll">
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 120 }}>Preview</th><th>Image</th><th>Dimensions</th>
                  <th className="r">Size</th><th>Recommended</th><th>Updated</th>
                  <th style={{ width: 120 }}><span className="sr">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {paged.slice.map((img) => (
                  <ImageRow key={img.name} img={img} busy={busy} onUpload={onUpload} />
                ))}
              </tbody>
            </table>
          </div>
          {images.length > 10 && (
            <Pager p={paged} noun="images" sizes={[10, 25]} style={{ padding: "14px 12px 0" }} />
          )}
        </>
      )}

      {docs.length > 0 && (
        <p className="faint" style={{ fontSize: 12.5, padding: "14px 12px 0" }}>
          Reference text files in the same folder:{" "}
          <span className="num">{docs.map((d) => `${d.name} (${d.size_kb} KB)`).join(", ")}</span>
        </p>
      )}
    </section>
  );
}
