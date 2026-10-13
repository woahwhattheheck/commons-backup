import React from 'react'
import { css } from '@emotion/core'

const icons = {
  github: (
    <path d="M12 .5A12 12 0 0 0 8.2 23.88c.6.1.82-.25.82-.58v-2.02c-3.34.72-4.04-1.42-4.04-1.42-.55-1.38-1.34-1.75-1.34-1.75-1.09-.75.08-.73.08-.73 1.2.08 1.84 1.24 1.84 1.24 1.08 1.83 2.82 1.3 3.5.99.11-.78.42-1.3.76-1.6-2.66-.3-5.46-1.33-5.46-5.93 0-1.3.47-2.38 1.24-3.22-.12-.3-.54-1.52.12-3.18 0 0 1.01-.32 3.3 1.23A11.5 11.5 0 0 1 12 6.5c1.02 0 2.04.14 3 .4 2.28-1.54 3.29-1.22 3.29-1.22.66 1.66.24 2.88.12 3.18.77.84 1.24 1.91 1.24 3.22 0 4.6-2.8 5.62-5.47 5.92.43.38.81 1.1.81 2.22v3.29c0 .32.22.69.83.58A12 12 0 0 0 12 .5z" />
  ),
  twitter: (
    <path d="M23.95 4.57a9.8 9.8 0 0 1-2.82.77 4.93 4.93 0 0 0 2.16-2.72 9.86 9.86 0 0 1-3.13 1.2 4.92 4.92 0 0 0-8.38 4.49A13.96 13.96 0 0 1 1.64 3.16a4.93 4.93 0 0 0 1.52 6.57A4.9 4.9 0 0 1 .93 9.1v.06a4.93 4.93 0 0 0 3.95 4.83 4.93 4.93 0 0 1-2.22.08 4.93 4.93 0 0 0 4.6 3.42A9.88 9.88 0 0 1 0 19.54a13.94 13.94 0 0 0 7.55 2.21c9.06 0 14.01-7.5 14.01-14.01v-.64a10 10 0 0 0 2.39-2.53z" />
  ),
  donate: (
    <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5A5.45 5.45 0 0 1 7.5 3c1.74 0 3.41.81 4.5 2.08A5.99 5.99 0 0 1 16.5 3 5.45 5.45 0 0 1 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
  ),
  link: (
    <path d="M3.9 12a5 5 0 0 1 5-5h4v2h-4a3 3 0 0 0 0 6h4v2h-4a5 5 0 0 1-5-5zm5.6 1h5v-2h-5v2zm1.6-6h4a5 5 0 0 1 0 10h-4v-2h4a3 3 0 0 0 0-6h-4V7z" />
  )
}

const labels = {
  github: 'GitHub',
  twitter: 'Twitter',
  donate: 'Donate',
  link: 'Link'
}

const normalizeLink = link => {
  if (typeof link === 'string') {
    return { url: link }
  }

  return link
}

export const SocialLinks = ({ links = [] }) => {
  const normalizedLinks = []
    .concat(links)
    .map(normalizeLink)
    .filter(link => link && link.url)

  if (normalizedLinks.length === 0) {
    return null
  }

  return (
    <div css={styles.links}>
      {normalizedLinks.map((link, index) => {
        const type = link.type || 'link'
        const label = link.label || labels[type] || labels.link
        return (
          <a
            key={`${link.url}-${index}`}
            css={styles.link}
            href={link.url}
            title={label}
            aria-label={label}
            target="_blank"
            rel="noopener noreferrer"
          >
            {link.icon || (
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                {icons[type] || icons.link}
              </svg>
            )}
          </a>
        )
      })}
    </div>
  )
}

const styles = {
  links: css`
    border-top: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    padding: 10px;
  `,
  link: css`
    width: 30px;
    height: 30px;
    border-radius: 3px;
    color: #777;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    text-decoration: none;
    transition: background 0.2s ease, color 0.2s ease;

    &:hover {
      background: rgba(0, 0, 0, 0.04);
      color: var(--theme-color);
    }

    & svg {
      width: 16px;
      height: 16px;
      fill: currentColor;
    }
  `
}
