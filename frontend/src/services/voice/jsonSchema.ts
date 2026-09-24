/**
 * TIDE Voice Agent - JSON Schema subset validator (pure, dependency-free).
 *
 * Mirrors backend/app/modules/voice/tools.py::validate_tool_args so the
 * browser re-validates model tool arguments against the schemas the backend
 * registered with the Realtime session BEFORE executing anything.
 *
 * Supported subset: type, enum, required, additionalProperties:false,
 * minimum, maximum, minLength, maxLength, nested $ref-free objects/arrays.
 */

export type Schema = Record<string, unknown>

const TYPE_CHECKS: Record<string, (v: unknown) => boolean> = {
  string: (v) => typeof v === 'string',
  number: (v) => typeof v === 'number' && Number.isFinite(v),
  integer: (v) => typeof v === 'number' && Number.isInteger(v),
  boolean: (v) => typeof v === 'boolean',
  object: (v) => v !== null && typeof v === 'object' && !Array.isArray(v),
  array: (v) => Array.isArray(v),
}

function checkValue(value: unknown, schema: Schema, path: string, errors: string[]): void {
  const type = typeof schema.type === 'string' ? schema.type : undefined
  const enumVals = Array.isArray(schema.enum) ? (schema.enum as unknown[]) : undefined

  if (type && !TYPE_CHECKS[type]?.(value)) {
    errors.push(`${path}: expected ${type}`)
    return
  }
  if (enumVals && !enumVals.some((e) => e === value)) {
    errors.push(`${path}: must be one of ${enumVals.map(String).join(', ')}`)
    return
  }
  if ((type === 'number' || type === 'integer') && typeof value === 'number') {
    const min = typeof schema.minimum === 'number' ? schema.minimum : undefined
    const max = typeof schema.maximum === 'number' ? schema.maximum : undefined
    if (min !== undefined && value < min) errors.push(`${path}: must be >= ${min}`)
    if (max !== undefined && value > max) errors.push(`${path}: must be <= ${max}`)
  }
  if (type === 'string' && typeof value === 'string') {
    const minLength = typeof schema.minLength === 'number' ? schema.minLength : undefined
    const maxLength = typeof schema.maxLength === 'number' ? schema.maxLength : undefined
    if (minLength !== undefined && value.length < minLength) {
      errors.push(`${path}: shorter than minLength`)
    }
    if (maxLength !== undefined && value.length > maxLength) {
      errors.push(`${path}: longer than maxLength`)
    }
  }
}

/** Validate one JSON value against a schema. Returns an array of errors (empty == valid). */
export function validateAgainst(value: unknown, schema: Schema): string[] {
  const errors: string[] = []
  if (!schema || typeof schema !== 'object') return ['schema: invalid schema object']
  if (schema.type === 'object') {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
      errors.push('value: expected object')
      return errors
    }
    const obj = value as Record<string, unknown>
    const props = (schema.properties ?? {}) as Record<string, Schema>
    const required = Array.isArray(schema.required) ? (schema.required as string[]) : []
    for (const key of required) {
      if (!(key in obj)) errors.push(`missing required argument '${key}'`)
    }
    for (const [key, val] of Object.entries(obj)) {
      if (key in props) {
        checkValue(val, props[key], key, errors)
      } else if (schema.additionalProperties === false) {
        errors.push(`unexpected argument '${key}'`)
      }
    }
    return errors
  }
  checkValue(value, schema, 'value', errors)
  return errors
}

export interface ToolSpecLike {
  name: string
  parameters: Schema
}

/** Validate tool arguments against a registry of specs (mirrors backend). */
export function validateToolArgs(
  tools: ToolSpecLike[],
  name: string,
  args: unknown,
): { ok: boolean; errors: string[] } {
  const spec = tools.find((t) => t.name === name)
  if (!spec) return { ok: false, errors: [`unknown tool '${name}'`] }
  if (args === undefined || args === null) args = {}
  if (typeof args !== 'object' || Array.isArray(args)) {
    return { ok: false, errors: ['arguments must be a JSON object'] }
  }
  const errors = validateAgainst(args, spec.parameters)
  return { ok: errors.length === 0, errors }
}

/** True when a value is a plain JSON object (used before dispatch). */
export function isPlainObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}