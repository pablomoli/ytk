// The hub's face, declared in theme.css. A canvas cannot read a custom
// property, so the stack is repeated here for the labels the scene draws.
export const DISPLAY = '"Besley", Georgia, serif';

// resolves once the face can be drawn into a canvas; a face that never arrives falls back
export async function displayReady(): Promise<void> {
  const drawn = Promise.all([document.fonts.load('540 16px "Besley"'), document.fonts.load('italic 540 16px "Besley"')]);
  await Promise.race([drawn.catch(() => undefined), new Promise((r) => window.setTimeout(r, 3000))]);
}
