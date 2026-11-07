import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { resolveLink } from '../logic'
import type { Block, Span, TextBlock } from '../types'

function classesFor(style: string): string {
  const names: string[] = []
  if (style.includes('b')) names.push('b')
  if (style.includes('i')) names.push('i')
  if (style.includes('c')) names.push('mono')
  return names.join(' ')
}

export function Rich({ spans }: { spans: Span[] }) {
  return (
    <>
      {spans.map((span, index) => {
        const className = classesFor(span[1])
        const href = span[2]
        if (href.startsWith('#')) {
          return (
            <Link key={index} to={resolveLink(href)} className={className || undefined}>
              {span[0]}
            </Link>
          )
        }
        if (!className) return <span key={index}>{span[0]}</span>
        return (
          <span key={index} className={className}>
            {span[0]}
          </span>
        )
      })}
    </>
  )
}

function textOf(block: TextBlock): string {
  return block.s.map((span) => span[0]).join('')
}

function TextView({ block }: { block: TextBlock }) {
  const body = <Rich spans={block.s} />
  switch (block.k) {
    case 'kicker':
      return <p className="kicker">{textOf(block)}</p>
    case 'h1':
      return <h1>{body}</h1>
    case 'h2':
      return (
        <h2 id={block.id || undefined}>
          <span className="rule" aria-hidden="true" />
          {body}
        </h2>
      )
    case 'h3':
      return <h3 id={block.id || undefined}>{body}</h3>
    case 'axiom':
      return <blockquote className="axiom">{body}</blockquote>
    case 'number':
      return <p className="number">{body}</p>
    case 'numsmall':
      return <p className="numsmall">{body}</p>
    default:
      return <p>{body}</p>
  }
}

function TableView({ block }: { block: Extract<Block, { k: 'table' }> }) {
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label="Table, scroll sideways if needed">
      <table>
        <tbody>
          {block.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => {
                const Tag = cell.h ? 'th' : 'td'
                return (
                  <Tag key={cellIndex} scope={cell.h ? 'col' : undefined}>
                    <Rich spans={cell.s} />
                  </Tag>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ContainerView({ block }: { block: Extract<Block, { k: 'callout' | 'card' }> }) {
  if (block.k === 'card') {
    return (
      <div className="callout card-block">
        <BlockList blocks={block.blocks} />
      </div>
    )
  }
  const tone = block.kind === 'warn' ? 'warn' : block.kind === 'good' ? 'good' : 'note'
  return (
    <aside className={`callout ${tone}`}>
      <p className="callout-label">{tone === 'warn' ? 'Caution' : 'Note'}</p>
      <BlockList blocks={block.blocks} />
    </aside>
  )
}

export function BlockView({ block }: { block: Block }) {
  if (block.k === 'table' && 'rows' in block) return <TableView block={block} />
  if ((block.k === 'callout' || block.k === 'card') && 'blocks' in block) return <ContainerView block={block} />
  return <TextView block={block as TextBlock} />
}

export function BlockList({ blocks }: { blocks: Block[] }) {
  const nodes: ReactNode[] = []
  let index = 0
  while (index < blocks.length) {
    const block = blocks[index]
    if (block.k === 'li') {
      const group: TextBlock[] = []
      while (index < blocks.length && blocks[index].k === 'li') {
        group.push(blocks[index] as TextBlock)
        index += 1
      }
      const ordered = group.some((item) => item.n != null)
      const Tag = ordered ? 'ol' : 'ul'
      nodes.push(
        <Tag key={`list-${index}`}>
          {group.map((item, itemIndex) => (
            <li key={itemIndex} value={item.n ?? undefined}>
              <Rich spans={item.s} />
            </li>
          ))}
        </Tag>,
      )
      continue
    }
    nodes.push(<BlockView key={index} block={block} />)
    index += 1
  }
  return <div className="prose">{nodes}</div>
}
