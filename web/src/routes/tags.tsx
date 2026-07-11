import { useEffect, useMemo, useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useApplyTagMerges, useProposeTagMerges, useTagMergeStatus } from '../api/tagMerge'
import type { EditableTagProposal } from '../lib/tagMerge'
import { editableProposals, mappingFromProposals } from '../lib/tagMerge'
import { HubControls } from '../components/HubControls'
import '../styles.css'

export const Route = createFileRoute('/tags')({ component: TagsPage })

function TagsPage() {
  const status = useTagMergeStatus()
  const propose = useProposeTagMerges()
  const apply = useApplyTagMerges()
  const [groups, setGroups] = useState<EditableTagProposal[]>([])
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (status.data?.state === 'done') {
      const proposals = status.data.proposals
      setGroups((current) => current.length ? current : editableProposals(proposals))
    }
  }, [status.data])

  const mapping = useMemo(() => mappingFromProposals(groups), [groups])
  const retired = Object.keys(mapping).length

  const updateGroup = (index: number, update: (group: EditableTagProposal) => EditableTagProposal) => {
    setGroups((current) => current.map((group, groupIndex) => groupIndex === index ? update(group) : group))
  }

  const makeCanonical = (index: number, tag: string) => updateGroup(index, (group) => ({
    ...group,
    canonical: tag,
    variants: [group.canonical, ...group.variants].filter((variant) => variant !== tag),
    excluded: new Set([...group.excluded].filter((variant) => variant !== tag)),
  }))

  const toggleExcluded = (index: number, tag: string) => updateGroup(index, (group) => {
    const excluded = new Set(group.excluded)
    if (excluded.has(tag)) excluded.delete(tag)
    else excluded.add(tag)
    return { ...group, excluded }
  })

  const start = () => {
    setMessage('')
    setGroups([])
    propose.mutate(undefined, { onError: (error) => setMessage(`failed to start: ${String(error)}`) })
  }

  const submit = () => {
    apply.mutate(mapping, {
      onSuccess: (result) => {
        setGroups([])
        setMessage(`applied: ${result.aliases} aliases saved, ${result.notes} notes rewritten, ${result.videos} index entries updated`)
      },
      onError: (error) => setMessage(`apply failed: ${String(error)}`),
    })
  }

  const stateMessage = status.data?.state === 'running'
    ? 'clustering + refining with haiku...'
    : status.data?.state === 'error'
      ? status.data.detail || 'proposal generation failed'
      : status.data?.state === 'done' && !status.data.proposals.length
        ? 'no merge candidates found — vocabulary is clean'
        : message

  return (
    <div className="tags-page">
      <HubControls>
        <span className="count">{groups.length ? `${groups.length} proposals` : ''}</span>
      </HubControls>
      <main className="tags-main">
        <div className="tag-actions">
          <button className="btn primary" type="button" onClick={start} disabled={propose.isPending || status.data?.state === 'running'}>Find merge candidates</button>
          <span className={status.data?.state === 'error' ? 'tag-error' : 'tag-status'}>{stateMessage}</span>
        </div>
        <p className="hint">Click a tag to make it the canonical name. Use × to keep a tag out of the merge. Nothing changes until Apply.</p>
        <div className="tag-groups">
          {groups.map((group, index) => (
            <section className={`tag-group${group.accepted ? '' : ' skipped'}`} key={`${group.canonical}-${index}`}>
              <div className="tag-group-row">
                <div className="chips">
                  {[group.canonical, ...group.variants].map((tag) => {
                    const canonical = tag === group.canonical
                    const excluded = group.excluded.has(tag)
                    return (
                      <span className={`tag-chip-wrap${excluded ? ' excluded' : ''}`} key={tag}>
                        <button
                          className={`tag-chip${canonical ? ' canonical' : ''}`}
                          type="button"
                          aria-pressed={canonical}
                          disabled={canonical}
                          onClick={() => canonical ? undefined : makeCanonical(index, tag)}
                        >
                          {tag} <span>{group.counts[tag] ?? ''}</span>
                        </button>
                        {!canonical ? <button className="tag-exclude" type="button" aria-label={`Exclude ${tag}`} onClick={() => toggleExcluded(index, tag)}>×</button> : null}
                      </span>
                    )
                  })}
                </div>
                <div className="tag-group-buttons">
                  <button className={`tag-group-button${group.accepted ? ' on' : ''}`} type="button" onClick={() => updateGroup(index, (current) => ({ ...current, accepted: true }))}>merge</button>
                  <button className={`tag-group-button${group.accepted ? '' : ' on'}`} type="button" onClick={() => updateGroup(index, (current) => ({ ...current, accepted: false }))}>skip</button>
                </div>
              </div>
            </section>
          ))}
        </div>
      </main>
      {groups.length ? (
        <div className="tag-apply-bar">
          <button className="btn primary" type="button" onClick={submit} disabled={!retired || apply.isPending}>Apply</button>
          <span>{retired ? `${retired} tags will be retired into ${new Set(Object.values(mapping)).size} canonical tags` : 'no merges selected'}</span>
        </div>
      ) : null}
    </div>
  )
}
