import { getStringPref } from "./prefs";

/* The prompt copied by every "ask" action. {id} is the vault-root-relative
   note path — the exact id vault_read accepts, so a paste into any Claude
   session resolves without translation. A template with no {id} degrades to
   "prompt + path" rather than silently dropping the id. */
export const ASK_PROMPT_PREF = "ytk:ask:prompt-template";
export const ASK_PROMPT_DEFAULT = "tell me something about {id}";

export function askPrompt(notePath: string): string {
  const template = getStringPref(ASK_PROMPT_PREF)?.trim() || ASK_PROMPT_DEFAULT;
  return template.includes("{id}")
    ? template.replaceAll("{id}", notePath)
    : `${template} ${notePath}`.trim();
}

export async function copyAskPrompt(notePath: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(askPrompt(notePath));
    return true;
  } catch {
    return false;
  }
}
