"""
Explainer skill: a narration becomes an animated explainer video (motion graphics in the style of the short animated
videos companies put on their websites) - independent of the demo-video and PPT skills.

  planner  one Azure OpenAI call splits the narration into scenes and decides what each shows (title, statement,
           points, stats, steps, compare, chart, icons, quote, closing); checked in code, facts only from the narration
  voice    Kokoro voices each scene with exact word timings; items appear when their words are said
  render   the scenes as an HTML player (web/), frames taken exactly in hidden browsers, MP4 with music and captions
  service  generate(): the whole pipeline, reusing the plan when only the look changes
"""
