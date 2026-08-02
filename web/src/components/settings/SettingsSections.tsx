import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import type { SettingsConfig } from "../../api/settings";
import { useGardenBuckets, useSaveGardenBuckets } from "../../api/profile";
import { ASK_PROMPT_DEFAULT, ASK_PROMPT_PREF } from "../../lib/askPrompt";
import { CURSOR_PREF, getPref, getStringPref, setPref, setStringPref } from "../../lib/prefs";

export type UpdateSettings = (update: (current: SettingsConfig) => void) => void;
type FieldError = (path: string) => string | undefined;
type PreviewResult = { winrate: number; ci?: [number, number]; faith_delta: number; n: number };

export function ChipList({
  values,
  onChange,
}: {
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const [value, setValue] = useState("");
  const add = () => {
    const next = value.trim().replace(/,$/, "");
    if (next) {
      onChange([...values, next]);
      setValue("");
    }
  };
  return (
    <span className="settings-chips">
      {values.map((item, index) => (
        <span className="settings-chip" key={`${item}-${index}`}>
          {item}
          <button
            type="button"
            aria-label={`Remove ${item}`}
            onClick={() => onChange(values.filter((_, itemIndex) => itemIndex !== index))}
          >
            ×
          </button>
        </span>
      ))}
      <input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onBlur={add}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === ",") {
            event.preventDefault();
            add();
          } else if (event.key === "Backspace" && !value && values.length)
            onChange(values.slice(0, -1));
        }}
        placeholder="add…"
      />
    </span>
  );
}

export function CheckList({
  values,
  options,
  onChange,
}: {
  values: string[];
  options: string[];
  onChange: (values: string[]) => void;
}) {
  return (
    <span className="settings-checks">
      {[...new Set([...options, ...values])].map((option) => (
        <label key={option}>
          <input
            type="checkbox"
            checked={values.includes(option)}
            onChange={(event) =>
              onChange(
                event.target.checked
                  ? [...values, option]
                  : values.filter((value) => value !== option),
              )
            }
          />
          {option}
        </label>
      ))}
    </span>
  );
}

export function HubSection({
  draft,
  update,
  fieldError,
}: {
  draft: SettingsConfig;
  update: UpdateSettings;
  fieldError: FieldError;
}) {
  return (
    <details open>
      <summary>Hub</summary>
      <div className="settings-body">
        <label>
          host
          <input
            value={draft.hub.host}
            className={fieldError("hub.host") ? "err" : ""}
            onChange={(event) =>
              update((config) => {
                config.hub.host = event.target.value;
              })
            }
          />
          <span className="settings-pill">restart required</span>
          {fieldError("hub.host") && <em>{fieldError("hub.host")}</em>}
        </label>
        <label>
          port
          <input
            type="number"
            value={draft.hub.port}
            className={fieldError("hub.port") ? "err" : ""}
            onChange={(event) =>
              update((config) => {
                config.hub.port = Number(event.target.value);
              })
            }
          />
          <span className="settings-pill">restart required</span>
          {fieldError("hub.port") && <em>{fieldError("hub.port")}</em>}
        </label>
        <label>
          tab icon
          <input
            value={draft.hub.favicon}
            maxLength={2}
            onChange={(event) =>
              update((config) => {
                config.hub.favicon = event.target.value;
              })
            }
          />
        </label>
        <label>
          tags
          <ChipList
            values={draft.hub.tags}
            onChange={(values) =>
              update((config) => {
                config.hub.tags = values;
              })
            }
          />
        </label>
        <label>
          pinterest feeds
          <ChipList
            values={draft.hub.pinterest_feeds}
            onChange={(values) =>
              update((config) => {
                config.hub.pinterest_feeds = values;
              })
            }
          />
        </label>
        <label>
          imessage gap (min)
          <input
            type="number"
            value={draft.hub.imessage_gap_minutes}
            onChange={(event) =>
              update((config) => {
                config.hub.imessage_gap_minutes = Number(event.target.value);
              })
            }
          />
        </label>
      </div>
    </details>
  );
}

export function CadenceSection({
  draft,
  update,
  onRefresh,
  refreshPending,
  refreshData,
}: {
  draft: SettingsConfig;
  update: UpdateSettings;
  onRefresh: () => void;
  refreshPending: boolean;
  refreshData?: Record<string, unknown> | undefined;
}) {
  return (
    <details open>
      <summary>Fetch cadence</summary>
      <div className="settings-body">
        {Object.entries(draft.hub.cadence_minutes).map(([source, minutes]) => (
          <label key={source}>
            {source}
            <input
              type="number"
              value={minutes}
              onChange={(event) =>
                update((config) => {
                  config.hub.cadence_minutes[source] = Number(event.target.value);
                })
              }
            />
          </label>
        ))}
        <button className="btn" type="button" onClick={onRefresh} disabled={refreshPending}>
          Pull all sources now
        </button>
        {refreshData && <span>{JSON.stringify(refreshData)}</span>}
      </div>
    </details>
  );
}

export function InterestSection({
  draft,
  update,
}: {
  draft: SettingsConfig;
  update: UpdateSettings;
}) {
  return (
    <details open>
      <summary>Interest model</summary>
      <div className="settings-body">
        <label>
          alpha
          <input
            type="number"
            step="0.5"
            value={draft.interest.alpha}
            onChange={(event) =>
              update((config) => {
                config.interest.alpha = Number(event.target.value);
              })
            }
          />
        </label>
        <label>
          explicit min
          <input
            type="number"
            value={draft.interest.explicit_min}
            onChange={(event) =>
              update((config) => {
                config.interest.explicit_min = Number(event.target.value);
              })
            }
          />
        </label>
        <label>
          cluster min
          <input
            type="number"
            value={draft.interest.cluster_min}
            onChange={(event) =>
              update((config) => {
                config.interest.cluster_min = Number(event.target.value);
              })
            }
          />
        </label>
        <label>
          cluster max
          <input
            type="number"
            value={draft.interest.cluster_max}
            onChange={(event) =>
              update((config) => {
                config.interest.cluster_max = Number(event.target.value);
              })
            }
          />
        </label>
        <label>
          content sources
          <CheckList
            values={draft.interest.content_sources}
            options={["instagram", "tiktok", "web", "pinterest", "imessage"]}
            onChange={(values) =>
              update((config) => {
                config.interest.content_sources = values;
              })
            }
          />
        </label>
      </div>
    </details>
  );
}

export function MapColorSection({
  draft,
  update,
  fieldError,
}: {
  draft: SettingsConfig;
  update: UpdateSettings;
  fieldError: FieldError;
}) {
  const [presetName, setPresetName] = useState("");
  const [preset, setPreset] = useState("");
  const updateRule = (index: number, rule: Partial<SettingsConfig["map"]["color_rules"][number]>) =>
    update((config) => {
      config.map.color_rules[index] = { ...config.map.color_rules[index], ...rule };
    });
  const moveRule = (index: number, direction: number) =>
    update((config) => {
      const next = index + direction;
      [config.map.color_rules[index], config.map.color_rules[next]] = [
        config.map.color_rules[next],
        config.map.color_rules[index],
      ];
    });

  return (
    <details open>
      <summary>Map color rules</summary>
      <div className="settings-body">
        {draft.map.color_rules.map((rule, index) => (
          <div className="rule" key={index}>
            <input
              type="color"
              value={rule.color}
              onChange={(event) => updateRule(index, { color: event.target.value })}
            />
            <input
              value={rule.query}
              className={fieldError(`map.color_rules.${index}`) ? "err" : ""}
              onChange={(event) => updateRule(index, { query: event.target.value })}
            />
            <button
              className="btn"
              type="button"
              disabled={!index}
              onClick={() => moveRule(index, -1)}
            >
              ↑
            </button>
            <button
              className="btn"
              type="button"
              disabled={index === draft.map.color_rules.length - 1}
              onClick={() => moveRule(index, 1)}
            >
              ↓
            </button>
            <button
              className="btn"
              type="button"
              onClick={() =>
                update((config) => {
                  config.map.color_rules.splice(index, 1);
                })
              }
            >
              ×
            </button>
          </div>
        ))}
        <button
          className="btn"
          type="button"
          onClick={() =>
            update((config) => {
              config.map.color_rules.push({ query: "", color: "#e2b04a" });
            })
          }
        >
          + rule
        </button>
        <div className="rule">
          <select value={preset} onChange={(event) => setPreset(event.target.value)}>
            <option value="">presets</option>
            {Object.keys(draft.map.presets).map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
          <button
            className="btn"
            type="button"
            disabled={!preset}
            onClick={() =>
              update((config) => {
                config.map.color_rules = structuredClone(config.map.presets[preset]);
              })
            }
          >
            Load
          </button>
          <button
            className="btn"
            type="button"
            disabled={!preset}
            onClick={() => {
              update((config) => {
                delete config.map.presets[preset];
              });
              setPreset("");
            }}
          >
            Delete
          </button>
          <input
            value={presetName}
            placeholder="save as…"
            onChange={(event) => setPresetName(event.target.value)}
          />
          <button
            className="btn"
            type="button"
            onClick={() => {
              if (!presetName) return;
              update((config) => {
                config.map.presets[presetName] = structuredClone(config.map.color_rules);
              });
              setPreset(presetName);
              setPresetName("");
            }}
          >
            Save preset
          </button>
        </div>
      </div>
    </details>
  );
}

export function IngestFiltersSection({
  draft,
  update,
}: {
  draft: SettingsConfig;
  update: UpdateSettings;
}) {
  return (
    <details open>
      <summary>Ingest filters</summary>
      <div className="settings-body">
        <label>
          min duration
          <input
            type="number"
            value={draft.filters.min_duration}
            onChange={(event) =>
              update((config) => {
                config.filters.min_duration = Number(event.target.value);
              })
            }
          />
        </label>
        <label>
          max duration
          <input
            type="number"
            value={draft.filters.max_duration ?? ""}
            onChange={(event) =>
              update((config) => {
                config.filters.max_duration =
                  event.target.value === "" ? null : Number(event.target.value);
              })
            }
          />
        </label>
        <label>
          require captions
          <input
            type="checkbox"
            checked={draft.filters.require_captions}
            onChange={(event) =>
              update((config) => {
                config.filters.require_captions = event.target.checked;
              })
            }
          />
        </label>
        <label>
          interest tags
          <ChipList
            values={draft.filters.interest_tags}
            onChange={(values) =>
              update((config) => {
                config.filters.interest_tags = values;
              })
            }
          />
        </label>
      </div>
    </details>
  );
}

export function MiscSection({ draft, update }: { draft: SettingsConfig; update: UpdateSettings }) {
  return (
    <details open>
      <summary>Misc</summary>
      <div className="settings-body">
        <label>
          whisper model
          <input
            value={draft.whisper_model}
            onChange={(event) =>
              update((config) => {
                config.whisper_model = event.target.value;
              })
            }
          />
        </label>
        <label>
          github repos
          <ChipList
            values={draft.github_repos}
            onChange={(values) =>
              update((config) => {
                config.github_repos = values;
              })
            }
          />
        </label>
        <label>
          memo notify
          <CheckList
            values={draft.memo_notify}
            options={["tmux", "macos", "sketchybar"]}
            onChange={(values) =>
              update((config) => {
                config.memo_notify = values;
              })
            }
          />
        </label>
      </div>
    </details>
  );
}

export function GardenBucketsSection() {
  const buckets = useGardenBuckets();
  const save = useSaveGardenBuckets();
  const [text, setText] = useState<string>();
  const [status, setStatus] = useState("");
  useEffect(() => {
    if (buckets.data && text === undefined) setText(buckets.data.text);
  }, [buckets.data, text]);
  if (text === undefined) return <div className="settings-body">loading buckets...</div>;
  const dirty = text !== (buckets.data?.text ?? "");
  const saveNow = () =>
    save.mutate(text, {
      onSuccess: (result) => setStatus(`saved ${result.buckets.length} buckets — ${result.hint}`),
      onError: (error) =>
        setStatus(
          error instanceof ApiError &&
            typeof error.body === "object" &&
            error.body &&
            "detail" in error.body
            ? String((error.body as { detail: unknown }).detail)
            : String(error),
        ),
    });
  return (
    <div className="settings-body">
      <p className="settings-hint">
        topic buckets for the garden — one tree per bucket ({buckets.data?.path}). yaml is saved
        verbatim, comments included; a save needs a garden rebuild to change the trees.
      </p>
      <textarea
        className="settings-yaml"
        spellCheck={false}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          setStatus("");
        }}
        rows={Math.min(30, text.split("\n").length + 2)}
      />
      <div className="rule">
        <button className="btn" type="button" disabled={!dirty || save.isPending} onClick={saveNow}>
          Save buckets
        </button>
        <span>{status}</span>
      </div>
    </div>
  );
}

export function EnvironmentSection({
  environment,
}: {
  environment?: Record<string, string | boolean> | undefined;
}) {
  return (
    <details>
      <summary>Environment</summary>
      <div className="settings-body">
        {environment ? (
          Object.entries(environment).map(([key, value]) => (
            <label key={key}>
              {key.replaceAll("_", " ")}
              <span className="settings-env">{String(value)}</span>
            </label>
          ))
        ) : (
          <span>unavailable</span>
        )}
      </div>
    </details>
  );
}

export function ToneSection({
  tone,
  onChange,
  onPreview,
  previewPending,
  previewData,
}: {
  tone: string;
  onChange: (tone: string) => void;
  onPreview: (tone: string) => void;
  previewPending: boolean;
  previewData?: PreviewResult | undefined;
}) {
  return (
    <details open>
      <summary>Enrichment tone</summary>
      <div className="settings-body">
        <label>
          tone
          <textarea value={tone} onChange={(event) => onChange(event.target.value)} />
        </label>
        <button
          className="btn"
          type="button"
          onClick={() => onPreview(tone)}
          disabled={previewPending}
        >
          Preview on 5 notes
        </button>
        {previewData && (
          <span>
            winrate {previewData.winrate.toFixed(2)}, ci{" "}
            {previewData.ci
              ? `[${previewData.ci[0].toFixed(2)}, ${previewData.ci[1].toFixed(2)}]`
              : "n/a"}
            , faith delta {previewData.faith_delta.toFixed(2)}, n={previewData.n}
          </span>
        )}
      </div>
    </details>
  );
}

export function AskPromptSection() {
  return (
    <details open>
      <summary>Ask prompt</summary>
      <div className="settings-body">
        <label>
          ask prompt
          <input
            defaultValue={getStringPref(ASK_PROMPT_PREF) ?? ""}
            placeholder={ASK_PROMPT_DEFAULT}
            onChange={(event) =>
              setStringPref(ASK_PROMPT_PREF, event.target.value.trim() ? event.target.value : null)
            }
          />
          <span className="settings-pill">{"{id}"} becomes the note path</span>
        </label>
      </div>
    </details>
  );
}

export function ExperimentsSection() {
  return (
    <details open>
      <summary>Experiments</summary>
      <div className="settings-body">
        <label>
          reticle cursor (feed + library)
          <input
            type="checkbox"
            defaultChecked={getPref(CURSOR_PREF)}
            onChange={(event) => setPref(CURSOR_PREF, event.target.checked)}
          />
          <span className="settings-pill">takes effect on next route visit</span>
        </label>
      </div>
    </details>
  );
}

export function SettingsSections({
  draft,
  update,
  fieldError,
  environment,
  onRefresh,
  refreshPending,
  refreshData,
  onPreview,
  previewPending,
  previewData,
}: {
  draft: SettingsConfig;
  update: UpdateSettings;
  fieldError: FieldError;
  environment?: Record<string, string | boolean> | undefined;
  onRefresh: () => void;
  refreshPending: boolean;
  refreshData?: Record<string, unknown> | undefined;
  onPreview: (tone: string) => void;
  previewPending: boolean;
  previewData?: PreviewResult | undefined;
}) {
  return (
    <>
      <HubSection draft={draft} update={update} fieldError={fieldError} />
      <CadenceSection
        draft={draft}
        update={update}
        onRefresh={onRefresh}
        refreshPending={refreshPending}
        refreshData={refreshData}
      />
      <InterestSection draft={draft} update={update} />
      <MapColorSection draft={draft} update={update} fieldError={fieldError} />
      <IngestFiltersSection draft={draft} update={update} />
      <MiscSection draft={draft} update={update} />
      <details open>
        <summary>Garden buckets</summary>
        <GardenBucketsSection />
      </details>
      <EnvironmentSection environment={environment} />
      <ToneSection
        tone={draft.hub.enrich_tone}
        onChange={(tone) =>
          update((config) => {
            config.hub.enrich_tone = tone;
          })
        }
        onPreview={onPreview}
        previewPending={previewPending}
        previewData={previewData}
      />
      <AskPromptSection />
      <ExperimentsSection />
    </>
  );
}
