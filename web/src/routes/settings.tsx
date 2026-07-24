import { useEffect, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { ApiError, apiSend } from "../api/client";
import { useSaveSettings, useSettings } from "../api/settings";
import { useGroveBuckets, useSaveGroveBuckets } from "../api/profile";
import type { ColorRule, SettingsConfig, SettingsValidationError } from "../api/settings";
import { cloneSettings, isDirty, validationByPath } from "../lib/settingsDraft";
import { CURSOR_PREF, getPref, setPref } from "../lib/prefs";
import { HubControls } from "../components/HubControls";
import "../styles.css";

export const Route = createFileRoute("/settings")({ component: SettingsPage });

function ChipList({
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
      {values.map((item, i) => (
        <span className="settings-chip" key={`${item}-${i}`}>
          {item}
          <button
            type="button"
            aria-label={`Remove ${item}`}
            onClick={() => onChange(values.filter((_, index) => index !== i))}
          >
            ×
          </button>
        </span>
      ))}
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={add}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            add();
          } else if (e.key === "Backspace" && !value && values.length)
            onChange(values.slice(0, -1));
        }}
        placeholder="add…"
      />
    </span>
  );
}

function CheckList({
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
            onChange={(e) =>
              onChange(
                e.target.checked ? [...values, option] : values.filter((value) => value !== option),
              )
            }
          />
          {option}
        </label>
      ))}
    </span>
  );
}

function GroveBucketsSection() {
  const buckets = useGroveBuckets();
  const save = useSaveGroveBuckets();
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
        topic buckets for the grove — one tree per bucket ({buckets.data?.path}). yaml is saved
        verbatim, comments included; a save needs a grove rebuild to change the trees.
      </p>
      <textarea
        className="settings-yaml"
        spellCheck={false}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
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

function SettingsPage() {
  const settings = useSettings();
  const save = useSaveSettings();
  const refresh = useMutation({
    mutationFn: () => apiSend<Record<string, unknown>>("/api/queue/refresh?force=true", "POST"),
  });
  const preview = useMutation({
    mutationFn: (tone: string) =>
      apiSend<{ winrate: number; ci?: [number, number]; faith_delta: number; n: number }>(
        "/api/enrich-preview",
        "POST",
        { tone },
      ),
  });
  const [draft, setDraft] = useState<SettingsConfig>();
  const [saved, setSaved] = useState<SettingsConfig>();
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [presetName, setPresetName] = useState("");
  const [preset, setPreset] = useState("");

  useEffect(() => {
    if (settings.data) {
      const next = cloneSettings(settings.data.config);
      setDraft(next);
      setSaved(cloneSettings(next));
    }
  }, [settings.data]);
  if (!draft || !saved)
    return (
      <div className="hub-page">
        <div className="hub-body">loading settings...</div>
      </div>
    );
  const dirty = isDirty(draft, saved);
  const set = (update: (current: SettingsConfig) => void) =>
    setDraft((current) => {
      const next = cloneSettings(current!);
      update(next);
      return next;
    });
  const fieldError = (path: string) =>
    errors[path] || Object.entries(errors).find(([key]) => key.startsWith(`${path}.`))?.[1];
  const saveDraft = () =>
    save.mutate(draft, {
      onSuccess: (result) => {
        setSaved(cloneSettings(draft));
        setErrors({});
        setMessage(
          result.restart_required ? "saved — run `ytk ui restart` to apply host/port" : "saved",
        );
      },
      onError: (error) => {
        if (
          error instanceof ApiError &&
          error.status === 422 &&
          typeof error.body === "object" &&
          error.body &&
          Array.isArray((error.body as { detail?: unknown }).detail)
        )
          setErrors(validationByPath((error.body as { detail: SettingsValidationError[] }).detail));
        else setMessage(`save failed: ${String(error)}`);
      },
    });
  const updateRule = (index: number, rule: Partial<ColorRule>) =>
    set((config) => {
      config.map.color_rules[index] = { ...config.map.color_rules[index], ...rule };
    });
  const moveRule = (index: number, direction: number) =>
    set((config) => {
      const next = index + direction;
      [config.map.color_rules[index], config.map.color_rules[next]] = [
        config.map.color_rules[next],
        config.map.color_rules[index],
      ];
    });
  const cadence = Object.entries(draft.hub.cadence_minutes);

  return (
    <div className="settings-page">
      <HubControls>
        <span className="count">~/.ytk/config.yaml</span>
      </HubControls>
      <main className="settings-main">
        <details open>
          <summary>Hub</summary>
          <div className="settings-body">
            <label>
              host
              <input
                value={draft.hub.host}
                className={fieldError("hub.host") ? "err" : ""}
                onChange={(e) =>
                  set((c) => {
                    c.hub.host = e.target.value;
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
                onChange={(e) =>
                  set((c) => {
                    c.hub.port = Number(e.target.value);
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
                onChange={(e) =>
                  set((c) => {
                    c.hub.favicon = e.target.value;
                  })
                }
              />
            </label>
            <label>
              tags
              <ChipList
                values={draft.hub.tags}
                onChange={(values) =>
                  set((c) => {
                    c.hub.tags = values;
                  })
                }
              />
            </label>
            <label>
              pinterest feeds
              <ChipList
                values={draft.hub.pinterest_feeds}
                onChange={(values) =>
                  set((c) => {
                    c.hub.pinterest_feeds = values;
                  })
                }
              />
            </label>
            <label>
              imessage gap (min)
              <input
                type="number"
                value={draft.hub.imessage_gap_minutes}
                onChange={(e) =>
                  set((c) => {
                    c.hub.imessage_gap_minutes = Number(e.target.value);
                  })
                }
              />
            </label>
          </div>
        </details>
        <details open>
          <summary>Fetch cadence</summary>
          <div className="settings-body">
            {cadence.map(([source, minutes]) => (
              <label key={source}>
                {source}
                <input
                  type="number"
                  value={minutes}
                  onChange={(e) =>
                    set((c) => {
                      c.hub.cadence_minutes[source] = Number(e.target.value);
                    })
                  }
                />
              </label>
            ))}
            <button
              className="btn"
              type="button"
              onClick={() => refresh.mutate()}
              disabled={refresh.isPending}
            >
              Pull all sources now
            </button>
            {refresh.data && <span>{JSON.stringify(refresh.data)}</span>}
          </div>
        </details>
        <details open>
          <summary>Interest model</summary>
          <div className="settings-body">
            <label>
              alpha
              <input
                type="number"
                step="0.5"
                value={draft.interest.alpha}
                onChange={(e) =>
                  set((c) => {
                    c.interest.alpha = Number(e.target.value);
                  })
                }
              />
            </label>
            <label>
              explicit min
              <input
                type="number"
                value={draft.interest.explicit_min}
                onChange={(e) =>
                  set((c) => {
                    c.interest.explicit_min = Number(e.target.value);
                  })
                }
              />
            </label>
            <label>
              cluster min
              <input
                type="number"
                value={draft.interest.cluster_min}
                onChange={(e) =>
                  set((c) => {
                    c.interest.cluster_min = Number(e.target.value);
                  })
                }
              />
            </label>
            <label>
              cluster max
              <input
                type="number"
                value={draft.interest.cluster_max}
                onChange={(e) =>
                  set((c) => {
                    c.interest.cluster_max = Number(e.target.value);
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
                  set((c) => {
                    c.interest.content_sources = values;
                  })
                }
              />
            </label>
          </div>
        </details>
        <details open>
          <summary>Map color rules</summary>
          <div className="settings-body">
            {draft.map.color_rules.map((rule, index) => (
              <div className="rule" key={index}>
                <input
                  type="color"
                  value={rule.color}
                  onChange={(e) => updateRule(index, { color: e.target.value })}
                />
                <input
                  value={rule.query}
                  className={fieldError(`map.color_rules.${index}`) ? "err" : ""}
                  onChange={(e) => updateRule(index, { query: e.target.value })}
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
                    set((c) => {
                      c.map.color_rules.splice(index, 1);
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
                set((c) => {
                  c.map.color_rules.push({ query: "", color: "#e2b04a" });
                })
              }
            >
              + rule
            </button>
            <div className="rule">
              <select value={preset} onChange={(e) => setPreset(e.target.value)}>
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
                  set((c) => {
                    c.map.color_rules = structuredClone(c.map.presets[preset]);
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
                  set((c) => {
                    delete c.map.presets[preset];
                  });
                  setPreset("");
                }}
              >
                Delete
              </button>
              <input
                value={presetName}
                placeholder="save as…"
                onChange={(e) => setPresetName(e.target.value)}
              />
              <button
                className="btn"
                type="button"
                onClick={() => {
                  if (presetName) {
                    set((c) => {
                      c.map.presets[presetName] = structuredClone(c.map.color_rules);
                    });
                    setPreset(presetName);
                    setPresetName("");
                  }
                }}
              >
                Save preset
              </button>
            </div>
          </div>
        </details>
        <details open>
          <summary>Ingest filters</summary>
          <div className="settings-body">
            <label>
              min duration
              <input
                type="number"
                value={draft.filters.min_duration}
                onChange={(e) =>
                  set((c) => {
                    c.filters.min_duration = Number(e.target.value);
                  })
                }
              />
            </label>
            <label>
              max duration
              <input
                type="number"
                value={draft.filters.max_duration ?? ""}
                onChange={(e) =>
                  set((c) => {
                    c.filters.max_duration = e.target.value === "" ? null : Number(e.target.value);
                  })
                }
              />
            </label>
            <label>
              require captions
              <input
                type="checkbox"
                checked={draft.filters.require_captions}
                onChange={(e) =>
                  set((c) => {
                    c.filters.require_captions = e.target.checked;
                  })
                }
              />
            </label>
            <label>
              interest tags
              <ChipList
                values={draft.filters.interest_tags}
                onChange={(values) =>
                  set((c) => {
                    c.filters.interest_tags = values;
                  })
                }
              />
            </label>
          </div>
        </details>
        <details open>
          <summary>Misc</summary>
          <div className="settings-body">
            <label>
              whisper model
              <input
                value={draft.whisper_model}
                onChange={(e) =>
                  set((c) => {
                    c.whisper_model = e.target.value;
                  })
                }
              />
            </label>
            <label>
              github repos
              <ChipList
                values={draft.github_repos}
                onChange={(values) =>
                  set((c) => {
                    c.github_repos = values;
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
                  set((c) => {
                    c.memo_notify = values;
                  })
                }
              />
            </label>
          </div>
        </details>
        <details open>
          <summary>Grove buckets</summary>
          <GroveBucketsSection />
        </details>
        <details>
          <summary>Environment</summary>
          <div className="settings-body">
            {settings.data?.meta.environment ? (
              Object.entries(settings.data.meta.environment).map(([key, value]) => (
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
        <details open>
          <summary>Enrichment tone</summary>
          <div className="settings-body">
            <label>
              tone
              <textarea
                value={draft.hub.enrich_tone}
                onChange={(e) =>
                  set((c) => {
                    c.hub.enrich_tone = e.target.value;
                  })
                }
              />
            </label>
            <button
              className="btn"
              type="button"
              onClick={() => preview.mutate(draft.hub.enrich_tone)}
              disabled={preview.isPending}
            >
              Preview on 5 notes
            </button>
            {preview.data && (
              <span>
                winrate {preview.data.winrate.toFixed(2)}, ci{" "}
                {preview.data.ci
                  ? `[${preview.data.ci[0].toFixed(2)}, ${preview.data.ci[1].toFixed(2)}]`
                  : "n/a"}
                , faith delta {preview.data.faith_delta.toFixed(2)}, n={preview.data.n}
              </span>
            )}
          </div>
        </details>
        <details open>
          <summary>Experiments</summary>
          <div className="settings-body">
            <label>
              reticle cursor (feed + library)
              <input
                type="checkbox"
                defaultChecked={getPref(CURSOR_PREF)}
                onChange={(e) => setPref(CURSOR_PREF, e.target.checked)}
              />
              <span className="settings-pill">takes effect on next route visit</span>
            </label>
          </div>
        </details>
      </main>
      {dirty && (
        <div className="settings-savebar">
          <button
            className="btn primary"
            type="button"
            onClick={saveDraft}
            disabled={save.isPending}
          >
            Save
          </button>
          <button
            className="btn"
            type="button"
            onClick={() => {
              setDraft(cloneSettings(saved));
              setErrors({});
              setMessage("");
            }}
          >
            Revert
          </button>
          <span>{message}</span>
        </div>
      )}
    </div>
  );
}
