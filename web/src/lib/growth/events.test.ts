import { expect, test } from 'vitest'
import { classifyEvent, dominantTags, joinEvidence, tagCountsOf, type LibraryItem } from './events'

const item = (stem: string, tags: string[], date: string): LibraryItem => ({
  stem,
  title: stem,
  url: null,
  tags,
  date,
  added: date,
  thumbnail: null,
  source: 'instagram',
})

const items = [
  item('b-2026-05-01-xyz', ['ai', 'cool-vis'], '2026-05-01'),
  item('a-2026-03-01-abc', ['creative-coding', 'cool-vis'], '2026-03-01'),
  item('c-2026-06-01-def', ['fitness'], '2026-06-01'),
]

test('joins chroma-style evidence ids to library stems, chronologically', () => {
  const joined = joinEvidence(
    ['note_sources_instagram_b-2026-05-01-xyz', 'note_sources_instagram_a-2026-03-01-abc'],
    items,
  )
  expect(joined.map((i) => i.stem)).toEqual(['a-2026-03-01-abc', 'b-2026-05-01-xyz'])
})

test('unmatched evidence ids are dropped', () => {
  expect(joinEvidence(['note_sources_youtube_missing'], items)).toEqual([])
})

test('dominant tags rank by frequency', () => {
  expect(dominantTags(items, 2)[0]).toBe('cool-vis')
})

test('classification: tag overlap with dominants means related', () => {
  const dom = ['cool-vis', 'creative-coding']
  expect(classifyEvent(['cool-vis', 'shaders'], dom)).toBe('related')
  expect(classifyEvent(['fitness'], dom)).toBe('novel')
  expect(classifyEvent([], dom)).toBe('novel')
})

test('tag counts accumulate across items', () => {
  expect(tagCountsOf(items)['cool-vis']).toBe(2)
})
