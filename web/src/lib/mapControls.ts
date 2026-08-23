import type { MapLayout } from "../api/map";

export type MapView = "all" | "content";
export type MapProjection = "2d" | "3d";
export type MapFilter = "signal" | "recent" | "media" | "time";
export type MapLayer = "terrain" | "web" | "fog" | "shell";

export type MapControlState = {
  view: MapView;
  projection: MapProjection;
  filters: Record<MapFilter, boolean>;
  layers: Record<MapLayer, boolean>;
  road: boolean;
};

export type MapControlAction =
  | { type: "set-view"; view: MapView }
  | { type: "set-projection"; projection: MapProjection }
  | { type: "toggle-filter"; filter: MapFilter }
  | { type: "toggle-layer"; layer: MapLayer }
  | { type: "toggle-road" }
  | { type: "reset" };

export function initialMapControls(hash = ""): MapControlState {
  return {
    view: hash === "#content" ? "content" : "all",
    projection: hash === "#2d" ? "2d" : "3d",
    filters: { signal: false, recent: false, media: false, time: false },
    layers: { terrain: false, web: false, fog: false, shell: false },
    road: false,
  };
}

export const resetMapControls = (): MapControlState => initialMapControls();

export function mapControlsReducer(
  state: MapControlState,
  action: MapControlAction,
): MapControlState {
  if (action.type === "reset") return resetMapControls();
  if (action.type === "set-view") return { ...state, view: action.view, road: false };
  if (action.type === "toggle-road") return { ...state, road: !state.road };
  if (action.type === "toggle-filter")
    return {
      ...state,
      filters: { ...state.filters, [action.filter]: !state.filters[action.filter] },
    };
  if (action.type === "set-projection")
    return action.projection === "2d"
      ? {
          ...state,
          projection: "2d",
          layers: { ...state.layers, web: false, fog: false, shell: false },
        }
      : { ...state, projection: "3d" };

  const enabled = !state.layers[action.layer];
  if (action.layer === "terrain")
    return {
      ...state,
      layers: enabled
        ? { terrain: true, web: false, fog: false, shell: false }
        : { ...state.layers, terrain: false },
    };
  if (action.layer === "web")
    return {
      ...state,
      projection: enabled ? "3d" : state.projection,
      layers: { ...state.layers, terrain: enabled ? false : state.layers.terrain, web: enabled },
    };
  if (action.layer === "fog")
    return {
      ...state,
      projection: enabled ? "3d" : state.projection,
      layers: {
        ...state.layers,
        terrain: enabled ? false : state.layers.terrain,
        fog: enabled,
        shell: enabled ? state.layers.shell : false,
      },
    };
  return {
    ...state,
    projection: enabled ? "3d" : state.projection,
    layers: {
      ...state.layers,
      terrain: enabled ? false : state.layers.terrain,
      fog: enabled || state.layers.fog,
      shell: enabled,
    },
  };
}

export function visibleMapLayers(
  layout: Pick<MapLayout, "terrain" | "web" | "fog">,
): Record<MapLayer, boolean> {
  return {
    terrain: Boolean(layout.terrain),
    web: Boolean(layout.web),
    fog: Boolean(layout.fog),
    shell: Boolean(layout.fog),
  };
}
