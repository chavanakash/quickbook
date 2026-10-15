import { describe, expect, it } from 'vitest'
import { formatCardNumber, formatDuration, luhnValid } from './utils.js'

describe('luhnValid', () => {
  it('accepts the test cards', () => {
    expect(luhnValid('4111 1111 1111 1111')).toBe(true)
    expect(luhnValid('4000000000000002')).toBe(true)
  })
  it('rejects bad numbers', () => {
    expect(luhnValid('4111111111111112')).toBe(false)
    expect(luhnValid('1234')).toBe(false)
  })
})

describe('formatting', () => {
  it('formats durations', () => {
    expect(formatDuration(147)).toBe('2h 27m')
    expect(formatDuration(60)).toBe('1h 00m')
  })
  it('groups card digits', () => {
    expect(formatCardNumber('4111111111111111')).toBe('4111 1111 1111 1111')
    expect(formatCardNumber('4111-11ab')).toBe('4111 11')
  })
})
