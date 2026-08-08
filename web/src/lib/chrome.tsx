import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

const ChromeContext = createContext(true);

// Default true so a route rendered outside the provider (every route test)
// keeps its controls.
export function useChromeVisible(): boolean {
  return useContext(ChromeContext);
}

const isTypingTarget = (target: EventTarget | null): boolean =>
  target instanceof HTMLElement &&
  (target.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

// Never persisted: a reload always restores the nav, so hidden chrome can't
// strand you on a page with no way out.
export function ChromeProvider({ children }: { children: ReactNode }) {
  const [visible, setVisible] = useState(
    () => new URLSearchParams(window.location.search).get("chrome") !== "0",
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "." || event.metaKey || event.ctrlKey || event.altKey)
        return;
      if (isTypingTarget(event.target)) return;
      event.preventDefault();
      setVisible((on) => !on);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <ChromeContext.Provider value={visible}>{children}</ChromeContext.Provider>
  );
}
