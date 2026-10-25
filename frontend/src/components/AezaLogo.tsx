/** Фирменный знак Aeza: компактная «é» → «aeza» (SVG и анимация как на aeza.net). */
const KEYS = [
  { src: '/brand/key-a.svg', className: 'aeza-key-a', width: 36, height: 36 },
  { src: '/brand/key-e.svg', className: 'aeza-key-e aeza-key-hero', width: 36, height: 36 },
  { src: '/brand/key-z.svg', className: 'aeza-key-z', width: 36, height: 36 },
  { src: '/brand/key-a-last.svg', className: 'aeza-key-a2', width: 36, height: 36 },
] as const

export function AezaLogo({ size = 'md' }: { size?: 'md' | 'sm' }) {
  return (
    <div className={`aeza-logo aeza-logo-intro aeza-logo-${size}`} role="img" aria-label="Aeza">
      <div className="aeza-logo-row" aria-hidden="true">
        {KEYS.map((key) => (
          <div key={key.src} className={`aeza-key-cell ${key.className}`}>
            <img src={key.src} alt="" width={key.width} height={key.height} decoding="async" draggable={false} />
          </div>
        ))}
      </div>
    </div>
  )
}
