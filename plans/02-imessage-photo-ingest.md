# [plan-02] iMessage / SMS Photo Ingestion — capture texted images into the pipeline

## Defect

The phase-7 iMessage capture pipeline reads text only. Photos the user texts to
themselves (references, whiteboards, project ideas, screenshots) are never ingested,
so a whole capture channel is dark. Six issues describe the same feature.

## Children

- #45 — expand memo capture to include text message images (master)
- #51 — picture/image capture to ytk pipeline
- #54 — image ingestion from text message photos
- #55 — ingest pictures from text messages
- #63 — SMS and iMessage photo ingestion
- #64 — extend iMessage pipeline to capture pictures

## Requirements

- Read image attachments from the Messages database (`~/Library/Messages/chat.db`
  + the `Attachments/` tree), scoped to self-sent / a designated capture thread,
  mirroring how the existing iMessage text capture selects messages.
- Run each image through the **existing** vision path (`vision.py` Claude image
  blocks) for a description + OCR, then store as an image atom with the attachment
  embedded (`![[...]]`) — reuse the Instagram/YouTube image-atom pattern, do not
  build a parallel one.
- Make the image searchable (visual embedding + text of the description) and
  routable through the standard `add` pipeline like other sources.

## Fix sequence

1. Extend the iMessage reader to enumerate attachment rows (MIME image/*), resolve
   file paths, and de-dup against already-ingested attachments.
2. Feed each image through `vision.py`; produce a source note under
   `sources/imessage/` with the image embedded and a description/OCR body.
3. Index: text embedding of the description + visual embedding of the image, with a
   canonical title (thread + date) — avoid the empty-metadata trap seen in
   Instagram notes (see plan-03).
4. Wire into the memo/capture entry point so texted photos are picked up on the same
   cadence as text captures.
5. Test with a fixture chat.db + attachment.

## Out of scope

- Non-image attachments (video, PDFs) — a later extension.
- The Instagram image-embed bug — tracked separately in plan-03, but this plan must
  reuse the same fixed image-atom builder once that lands.

## Dependency

Coordinate with **plan-03** (Instagram ingestion): both should share one image-atom
note builder and one indexing path so metadata bugs are fixed once.
