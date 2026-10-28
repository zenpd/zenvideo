"""
PPT skill: a narration, call transcript or notes in, a strong pitch deck (.pptx) out - independent of the video skill
(demo/). Optional screenshots of the app from its link.

  source    clean the pasted text (stage directions, speaker labels, timestamps, subtitles, filler)
  writer    one Azure OpenAI call plans and writes the deck; code checks it (no invented numbers)
  designs   6 designs x 10 slide types (+ cover, agenda, closing)
  capture   optional: screens of the app from its link, captured once
  service   generate(): material -> deck, reusing the story when only the design changes
  api       FastAPI router /api/ppt (decks, designs, sample decks)

    python -m ppt narration.txt --template consulting
"""
