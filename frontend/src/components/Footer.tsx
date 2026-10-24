export function Footer() {
  return (
    <footer className="shrink-0 border-t border-rule bg-paper px-4 py-3 text-ink desk:px-6">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-1 text-sm text-ink-soft">
        <div className="footer-brand min-w-0 desk-only">
          <p className="font-serif text-base font-medium leading-none tracking-tight text-ink">Invoice Keeper</p>
          <p className="footer-tagline mt-1 max-w-md text-xs leading-snug">
            Регулярные платежи команды под контролем.
          </p>
        </div>
        <p className="num shrink-0 text-xs">2026 · Aeza</p>
      </div>
    </footer>
  )
}
