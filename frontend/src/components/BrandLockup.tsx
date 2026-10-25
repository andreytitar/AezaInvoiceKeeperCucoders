import type { ReactNode } from 'react'
import { AezaLogo } from './AezaLogo'

type Props = {
  /** Без подписи «Регулярные платежи…» (шапка входа). */
  compact?: boolean
  className?: string
  children?: ReactNode
}

/** Логотип Aeza с анимацией раскрытия; название продукта — под знаком. */
export function BrandLockup({ compact = false, className = '', children }: Props) {
  return (
    <div className={`shell-brand-stack brand-lockup-intro ${className}`.trim()}>
      <AezaLogo size={compact ? 'sm' : 'md'} />
      <div className="brand-product">
        <p className={`brand-name ${compact ? 'brand-name-header' : ''}`}>Invoice Keeper</p>
        {!compact && <p className="brand-caption">Регулярные платежи команды</p>}
      </div>
      {children}
    </div>
  )
}
