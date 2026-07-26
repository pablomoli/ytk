import { useEffect, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { ApiError, apiSend } from "../api/client";
import { useSaveSettings, useSettings } from "../api/settings";
import type { SettingsConfig, SettingsValidationError } from "../api/settings";
import { cloneSettings, isDirty, validationByPath } from "../lib/settingsDraft";
import { HubControls } from "../components/HubControls";
import { SettingsSections } from "../components/settings/SettingsSections";
import "../styles.css";

export const Route = createFileRoute("/settings")({ component: SettingsPage });

export function SettingsPage() {
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
  const update = (change: (current: SettingsConfig) => void) =>
    setDraft((current) => {
      const next = cloneSettings(current!);
      change(next);
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

  return (
    <div className="settings-page">
      <HubControls>
        <span className="count">~/.ytk/config.yaml</span>
      </HubControls>
      <main className="settings-main">
        <SettingsSections
          draft={draft}
          update={update}
          fieldError={fieldError}
          environment={settings.data?.meta.environment}
          onRefresh={() => refresh.mutate()}
          refreshPending={refresh.isPending}
          refreshData={refresh.data}
          onPreview={(tone) => preview.mutate(tone)}
          previewPending={preview.isPending}
          previewData={preview.data}
        />
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
