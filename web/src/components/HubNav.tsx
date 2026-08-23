import { CaretDownIcon } from "@phosphor-icons/react";
import { Link, useLocation } from "@tanstack/react-router";
import { Button } from "./ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

type NavDestination = {
  label: string;
  to:
    | "/"
    | "/inbox"
    | "/library"
    | "/map"
    | "/recs"
    | "/channels"
    | "/profile"
    | "/orb"
    | "/galaxy"
    | "/atlas"
    | "/garden"
    | "/growth"
    | "/docs"
    | "/tags"
    | "/settings";
  section: "core" | "Learn and curate" | "Labs" | "Maintain";
};

export const HUB_DESTINATIONS = [
  { label: "Fresh", to: "/", section: "core" },
  { label: "Inbox", to: "/inbox", section: "core" },
  { label: "Library", to: "/library", section: "core" },
  { label: "Map", to: "/map", section: "core" },
  { label: "Recs", to: "/recs", section: "Learn and curate" },
  { label: "Creators", to: "/channels", section: "Learn and curate" },
  { label: "Profile", to: "/profile", section: "Learn and curate" },
  { label: "Orb", to: "/orb", section: "Labs" },
  { label: "Galaxy", to: "/galaxy", section: "Labs" },
  { label: "Atlas", to: "/atlas", section: "Labs" },
  { label: "Garden", to: "/garden", section: "Labs" },
  { label: "Growth", to: "/growth", section: "Labs" },
  { label: "Docs", to: "/docs", section: "Labs" },
  { label: "Tag cleanup", to: "/tags", section: "Maintain" },
  { label: "Settings", to: "/settings", section: "Maintain" },
] satisfies readonly NavDestination[];

const core = HUB_DESTINATIONS.filter((item) => item.section === "core");
const groups = (["Learn and curate", "Labs", "Maintain"] as const).map((section) => ({
  section,
  destinations: HUB_DESTINATIONS.filter((item) => item.section === section),
}));

const linkClass =
  "inline-flex min-h-11 items-center rounded-md px-3 sm:min-h-8 font-data text-sm tracking-[0.03em] text-ink2 no-underline lowercase hover:bg-bg3 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent [&.active]:font-semibold [&.active]:text-live [&.active]:underline [&.active]:decoration-2 [&.active]:underline-offset-4";

export function HubNav() {
  const pathname = useLocation().pathname;
  const secondaryActive = HUB_DESTINATIONS.some(
    (item) => item.section !== "core" && pathname.startsWith(item.to),
  );

  return (
    <>
      <a
        href="#main-content"
        className="fixed top-2 left-2 z-50 -translate-y-20 rounded-md bg-accent px-3 py-2 font-data text-bg0 transition-transform focus:translate-y-0"
      >
        Skip to content
      </a>
      <nav
        className="flex min-w-0 flex-wrap items-center gap-1"
        aria-label="Hub navigation"
      >
        {core.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            activeOptions={{ exact: item.to === "/" }}
            activeProps={{ className: "active" }}
            className={linkClass}
          >
            {item.label}
          </Link>
        ))}
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="ghost"
              aria-label={secondaryActive ? "More, current section" : "More"}
              data-active={secondaryActive}
              className="gap-1 sm:min-h-8! data-[active=true]:font-semibold data-[active=true]:text-live data-[active=true]:underline data-[active=true]:decoration-2 data-[active=true]:underline-offset-4"
            >
              More
              <CaretDownIcon aria-hidden="true" className="size-4" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="grid w-auto grid-cols-3 gap-x-6 p-3" align="start">
            {groups.map((group) => (
              <section key={group.section}>
                <h2 className="m-0 px-2 py-1 font-data! text-xs! font-semibold! tracking-[0.08em] text-mute! uppercase">
                  {group.section}
                </h2>
                <div className="flex flex-col">
                  {group.destinations.map((item) => (
                    <Link
                      key={item.to}
                      to={item.to}
                      activeProps={{ className: "active" }}
                      className={linkClass}
                    >
                      {item.label}
                    </Link>
                  ))}
                </div>
              </section>
            ))}
          </PopoverContent>
        </Popover>
      </nav>
    </>
  );
}
