export function StageConfig({ fields, values, onChange, colors }) {
  return (
    <div className={`px-5 pb-5 pt-4 grid grid-cols-1 sm:grid-cols-2 gap-x-5 gap-y-4
                     border-t border-gray-100 ${colors.cfg_bg}`}>
      {fields.map((field) => (
        <div key={field.key}>
          <label className="label">{field.label}</label>

          {field.type === 'select' ? (
            <select
              value={values[field.key] ?? field.default}
              onChange={(e) => onChange(field.key, e.target.value)}
              className="input"
            >
              {field.options.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          ) : (
            <input
              type={field.type === 'number' ? 'number' : 'text'}
              value={values[field.key] ?? field.default}
              min={field.min}
              max={field.max}
              step={field.step ?? (field.type === 'number' ? 1 : undefined)}
              onChange={(e) =>
                onChange(
                  field.key,
                  field.type === 'number'
                    ? (field.step && field.step < 1
                        ? parseFloat(e.target.value)
                        : parseInt(e.target.value, 10))
                    : e.target.value,
                )
              }
              className="input"
            />
          )}

          {field.help && (
            <p className="mt-1 text-[11px] text-gray-400">{field.help}</p>
          )}
        </div>
      ))}
    </div>
  )
}
