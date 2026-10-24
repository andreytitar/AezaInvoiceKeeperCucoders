import type { SVGProps } from 'react'

const paths = {
  wallet:
    'M4 4h14a2 2 0 0 1 2 2v2H5a1 1 0 0 0 0 2h15v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Zm13 9a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Z',
  calendar:
    'M6 2a1 1 0 0 1 1 1v1h10V3a1 1 0 1 1 2 0v1h1a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h1V3a1 1 0 0 1 1-1ZM4 9v11h16V9H4Zm3 3h3v3H7v-3Zm7 0h3v3h-3v-3Z',
  budget: 'M11 2v10h10A10 10 0 1 1 11 2Zm3 0a10 10 0 0 1 8 8h-8V2Z',
  repeat:
    'M6 4h10V2a.7.7 0 0 1 1.2-.5l4 4a.7.7 0 0 1 0 1l-4 4A.7.7 0 0 1 16 10V8H6a2 2 0 0 0-2 2v2H1v-2a6 6 0 0 1 5-6Zm12 16H8v2a.7.7 0 0 1-1.2.5l-4-4a.7.7 0 0 1 0-1l4-4A.7.7 0 0 1 8 14v2h10a2 2 0 0 0 2-2v-2h3v2a6 6 0 0 1-5 6Z',
  users:
    'M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8Zm8 1a3.5 3.5 0 1 1-1 6.9 6 6 0 0 0 0-6.8l1-.1ZM9 13c5 0 7 3 7 6v2H2v-2c0-3 2-6 7-6Zm8 0c4 0 5 3 5 6v2h-4v-2c0-2.3-.7-4.3-2-5.8l1-.2Z',
  webhook:
    'M12 2a5 5 0 0 1 4 8l-2-1a2.5 2.5 0 1 0-4 0l-3 5a2 2 0 1 0 2 2h2a4 4 0 1 1-6-3l2-4a5 5 0 0 1 5-7Zm2 10 2-1 2 3a4 4 0 1 1-1 7h-6v-2h6a2 2 0 1 0-1-3l-2-4Z',
  audit: 'M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm8 2v5h5l-5-5ZM8 12v2h8v-2H8Zm0 4v2h6v-2H8Z',
  sun: 'M12 7a5 5 0 1 1 0 10 5 5 0 0 1 0-10Zm-1-6h2v4h-2V1Zm0 18h2v4h-2v-4ZM1 11h4v2H1v-2Zm18 0h4v2h-4v-2ZM4 3l3 3-1 1-3-3 1-1Zm13 14 3 3 1-1-3-3-1 1ZM3 20l3-3 1 1-3 3-1-1ZM17 6l3-3 1 1-3 3-1-1Z',
  moon: 'M21 14A9 9 0 0 1 10 3a9.5 9.5 0 1 0 11 11Z',
  logout: 'M4 2h8v3H5v14h7v3H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm11 4 7 6-7 6v-4H9v-4h6V6Z',
  telegram:
    'm21.8 3.2-3.3 17c-.2 1-1 1.2-1.8.7l-5-3.7-2.4 2.3c-.3.3-.5.5-1 .5l.4-5.2 9.5-8.6c.4-.4-.1-.6-.6-.3L5.9 13.3l-5-1.6c-1.1-.3-1.1-1.1.2-1.6L20.5 2.6c.9-.3 1.6.2 1.3.6Z',
  more: 'M5 10a2 2 0 1 1 0 4 2 2 0 0 1 0-4Zm7 0a2 2 0 1 1 0 4 2 2 0 0 1 0-4Zm7 0a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z',
  'chevron-left': 'm15 4 2 2-6 6 6 6-2 2-8-8 8-8Z',
  'chevron-right': 'm9 4-2 2 6 6-6 6 2 2 8-8-8-8Z',
  plus: 'M10.5 3h3v7.5H21v3h-7.5V21h-3v-7.5H3v-3h7.5V3Z',
  check: 'm9 16-5-5-2 2 7 7L22 7l-2-2L9 16Z',
  receipt: 'M5 2h14v20l-3-2-4 2-4-2-3 2V2Zm3 5v2h8V7H8Zm0 4v2h8v-2H8Zm0 4v2h5v-2H8Z',
  edit: 'm16 2 6 6-13 13H3v-6L16 2ZM5 16v3h3L18 9l-3-3L5 16Z',
  trash: 'M8 2h8v3h5v2H3V5h5V2Zm-3 7h14l-1 13H6L5 9Zm4 2v8h2v-8H9Zm4 0v8h2v-8h-2Z',
  filter: 'M2 3h20v3l-8 8v7l-4-2v-5L2 6V3Z',
  search: 'M10 2a8 8 0 1 1-4.9 14.3L1 20.4 3.6 23l4.2-4.2A8 8 0 0 1 10 2Zm0 3a5 5 0 1 0 0 10 5 5 0 0 0 0-10Z',
  close: 'm5 3 7 7 7-7 2 2-7 7 7 7-2 2-7-7-7 7-2-2 7-7-7-7 2-2Z',
  'arrow-up': 'm12 2 9 9-2 2-5.5-5.5V22h-3V7.5L5 13l-2-2 9-9Z',
  link: 'm13 4 2-2a5.7 5.7 0 0 1 8 8l-5 5a5.7 5.7 0 0 1-8 0l2-2a2.8 2.8 0 0 0 4 0l5-5a2.8 2.8 0 0 0-4-4l-2 2-2-2ZM1 14l5-5a5.7 5.7 0 0 1 8 0l-2 2a2.8 2.8 0 0 0-4 0l-5 5a2.8 2.8 0 0 0 4 4l2-2 2 2-2 2a5.7 5.7 0 0 1-8-8Z',
  shield: 'm12 1 9 4v7c0 6-9 11-9 11S3 18 3 12V5l9-4Zm-1 15 6-6-2-2-4 4-2-2-2 2 4 4Z',
  clock: 'M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20Zm-1 4v7l5 3 1-2-4-2V6h-2Z',
  bell: 'M12 2a6 6 0 0 1 6 6v5l3 4v2H3v-2l3-4V8a6 6 0 0 1 6-6ZM9 21h6a3 3 0 0 1-6 0Z',
}
export type IconName = keyof typeof paths
export function Icon({ name, className = '', ...props }: SVGProps<SVGSVGElement> & { name: IconName }) {
  return (
    <svg
      {...props}
      className={`icon ${className}`}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
    >
      <path d={paths[name]} fillRule="evenodd" />
    </svg>
  )
}
