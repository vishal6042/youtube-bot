import { Btn } from "../../ui.jsx";

/* Footer for the cards that edit channel text and playlists. They share one
   save, because the server stores both in a single request. */
export default function SaveBar({ dirty, busy, onSave, onDiscard, note, bare }) {
  return (
    <div className="card-foot" style={bare ? { marginTop: 0, paddingTop: 0, borderTop: 0 } : undefined}>
      <span className="note">{note}</span>
      <Btn disabled={!dirty || busy} onClick={onDiscard}>Discard changes</Btn>
      <Btn kind="primary" icon={dirty ? undefined : "check"} disabled={!dirty || busy} onClick={onSave}>
        {busy && dirty ? "Saving" : dirty ? "Save changes" : "Saved"}
      </Btn>
    </div>
  );
}
