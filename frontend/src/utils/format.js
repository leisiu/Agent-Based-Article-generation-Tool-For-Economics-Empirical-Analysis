/**
 * 数字格式化工具
 * - 兼容 null/undefined/NaN
 * - 数字保留指定小数位
 * - 非数字返回 '-'
 */
export function fmtNum(val, digits = 4) {
  if (val === undefined || val === null || val === '') return '-'
  const n = Number(val)
  if (!isFinite(n) || isNaN(n)) return '-'
  return n.toFixed(digits)
}
