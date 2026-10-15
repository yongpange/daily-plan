// 今日视图任务树的本地辅助 —— 平移 web-legacy/app.js 的 entriesInTreeOrder /
// threadTaskIds / entriesUnderTask / outcomeLabels。
// 运行时 outcome 含 planned / carried / rescheduled，统一用 outcomeText() 取值后比较。
import type { Entry } from '../../types/api'

export const outcomeLabels: Record<string, string> = {
  carried: '已顺延',
  rescheduled: '已改期',
  abandoned: '已放弃',
}

/** 运行时 outcome 字符串（含 planned / carried / rescheduled） */
export function outcomeText(entry: Entry): string {
  return (entry.outcome ?? '') as string
}

export function isPlanned(entry: Entry): boolean {
  const outcome = outcomeText(entry)
  return !outcome || outcome === 'planned'
}

export function isCompleted(entry: Entry): boolean {
  return outcomeText(entry) === 'completed'
}

export function isFinished(entry: Entry): boolean {
  return !isPlanned(entry)
}

export interface TreeRow {
  entry: Entry
  depth: number
}

/** 平移 entriesInTreeOrder：顶层保持原序，子任务紧随父任务（孤儿父按顶层处理） */
export function entriesInTreeOrder(entries: Entry[]): TreeRow[] {
  const byTask = new Map(entries.map((entry) => [entry.task_id, entry]))
  const children = new Map<number | null, Entry[]>()
  entries.forEach((entry) => {
    const parentKey = entry.parent_id != null && byTask.has(entry.parent_id) ? entry.parent_id : null
    const list = children.get(parentKey)
    if (list) list.push(entry)
    else children.set(parentKey, [entry])
  })
  const result: TreeRow[] = []
  const visit = (parentKey: number | null, depth: number) => {
    for (const entry of children.get(parentKey) ?? []) {
      result.push({ entry, depth: Math.min(depth, 3) })
      visit(entry.task_id, depth + 1)
    }
  }
  visit(null, 0)
  return result
}

/** 平移 entriesUnderTask：rootTaskId 及其全部后代条目 */
export function entriesUnderTask(rootTaskId: number | null, entries: Entry[]): Entry[] {
  const ids = new Set<number>([Number(rootTaskId)])
  let growing = true
  while (growing) {
    growing = false
    entries.forEach((entry) => {
      if (entry.parent_id != null && ids.has(entry.parent_id) && entry.task_id != null && !ids.has(entry.task_id)) {
        ids.add(entry.task_id)
        growing = true
      }
    })
  }
  return entries.filter((entry) => entry.task_id != null && ids.has(entry.task_id))
}

/** 平移 threadTaskIds：所有主线条目的家族（主线根 + 全部后代）task_id 集合 */
export function threadTaskIds(entries: Entry[]): Set<number> {
  const roots = new Set(
    entries
      .filter((entry) => entry.thread_id != null && entry.task_id != null)
      .map((entry) => entry.task_id as number),
  )
  const children = new Map<number, number[]>()
  entries.forEach((entry) => {
    if (entry.parent_id == null || entry.task_id == null) return
    const list = children.get(entry.parent_id)
    if (list) list.push(entry.task_id)
    else children.set(entry.parent_id, [entry.task_id])
  })
  const family = new Set<number>(roots)
  const stack = [...roots]
  while (stack.length) {
    const taskId = stack.pop()!
    for (const child of children.get(taskId) ?? []) {
      if (!family.has(child)) {
        family.add(child)
        stack.push(child)
      }
    }
  }
  return family
}
