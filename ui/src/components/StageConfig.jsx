import { VoiceSelector } from './VoiceSelector'
import { FilePicker } from './FilePicker'
export function StageConfig({ fields, values, onChange, colors }) {
  return (
    <div
      className={`px-5 pb-5 pt-4 grid grid-cols-1 sm:grid-cols-2 gap-x-5 gap-y-4
                  border-t border-gray-100 ${colors.cfg_bg}`}
    >
      {fields.map((field) => (
        <div key={field.key}>
          <label className="label">{field.label}</label>

          {/* Stage output - read-only connection */}
          {field.type === 'stage_output' ? (
            <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-700">
                    Stage {field.sourceStage} output
                  </p>

                  <p className="mt-1 truncate font-mono text-xs text-gray-500">
                    {field.sourceOutput}
                  </p>
                </div>

                <span className="shrink-0 rounded-full bg-green-50 px-2.5 py-1 text-xs font-medium text-green-700">
                  Connected
                </span>
              </div>
            </div>

          ) : field.key === 'voice' ? (

            <VoiceSelector
              value={values[field.key] ?? field.default}
              onChange={(value) => onChange(field.key, value)}
              speed={values.speed}
              lang={values.lang}
            />

          ) : field.type === 'select' ? (

            <select
              value={values[field.key] ?? field.default}
              onChange={(e) =>
                onChange(field.key, e.target.value)
              }
              className="input"
            >
              {field.options.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>

          ) : field.type === 'text' ? (

            <FilePicker
              value={values[field.key] ?? field.default}
              onChange={(val) => onChange(field.key, val)}
              fileExts={field.fileExts || ''}
              placeholder={field.default}
            />

          ) : (

            <input
              type="number"
              value={
                values[field.key] ?? field.default
              }
              min={field.min}
              max={field.max}
              step={
                field.step ?? 1
              }
              onChange={(e) =>
                onChange(
                  field.key,
                  (field.step && field.step < 1)
                    ? parseFloat(e.target.value)
                    : parseInt(e.target.value, 10),
                )
              }
              className="input"
            />

          )}

          {field.help && (
            <p className="mt-1 text-[11px] text-gray-400">
              {field.help}
            </p>
          )}
        </div>
      ))}
    </div>
  )
}