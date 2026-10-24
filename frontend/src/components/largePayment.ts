/** Пороги второго подтверждения. Суммы разных валют не конвертируются. */
const LARGE_PAYMENT: Record<string, string> = {
  RUB: '10000',
  USD: '100',
  EUR: '100',
}

function cmpDecimal(a: string, b: string): number | null {
  const parse = (raw: string) => {
    const match = raw.trim().replace(/\s+/g, '').match(/^([+-])?(\d+)(?:\.(\d+))?$/)
    if (!match) return null
    return {
      neg: match[1] === '-',
      int: match[2].replace(/^0+(?=\d)/, '') || '0',
      frac: match[3] ?? '',
    }
  }
  const left = parse(a)
  const right = parse(b)
  if (!left || !right) return null
  if (left.neg !== right.neg) return left.neg ? -1 : 1
  const sign = left.neg ? -1 : 1
  if (left.int.length !== right.int.length) return sign * (left.int.length - right.int.length)
  if (left.int !== right.int) return sign * (left.int < right.int ? -1 : 1)
  const scale = Math.max(left.frac.length, right.frac.length)
  const lf = left.frac.padEnd(scale, '0')
  const rf = right.frac.padEnd(scale, '0')
  if (lf === rf) return 0
  return sign * (lf < rf ? -1 : 1)
}

/** Крупная ещё не оплаченная сумма: перед запросом нужно второе подтверждение. */
export function needsPayConfirm(status: string, amount: string, currency: string): boolean {
  if (status === 'paid') return false
  const threshold = LARGE_PAYMENT[currency]
  if (!threshold) return false
  const cmp = cmpDecimal(amount, threshold)
  return cmp !== null && cmp >= 0
}
