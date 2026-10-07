# Step Audio EditX Catalog

Use only implemented values.

## Edit routes

- `emotion`, `style`, `speed`, `paralinguistic`, `denoise`, `vad`: Step Audio EditX
- `voice`: ChatterBox voice conversion route

## Emotions

`happy`, `sad`, `angry`, `excited`, `calm`, `fearful`, `surprised`, `disgusted`, `confusion`, `empathy`, `embarrass`, `depressed`, `coldness`, `admiration`, `remove`

## Styles

`whisper`, `serious`, `child`, `older`, `girl`, `pure`, `sister`, `sweet`, `exaggerated`, `ethereal`, `generous`, `recite`, `act_coy`, `warm`, `shy`, `comfort`, `authority`, `chat`, `radio`, `soulful`, `gentle`, `story`, `vivid`, `program`, `news`, `advertising`, `roar`, `murmur`, `shout`, `deeply`, `loudly`, `arrogant`, `friendly`, `remove`

## Speed values

The editor UI displays `faster`, `slower`, `more faster`, and `more slower`. Inline tags/documentation use underscore forms `more_faster` and `more_slower`. For JSON passed to the editor driver, prefer the UI forms with spaces.

## Paralinguistic tags

`Laughter`, `Breathing`, `Sigh`, `Uhm`, `Surprise-oh`, `Surprise-ah`, `Surprise-wa`, `Confirmation-en`, `Question-ei`, `Dissatisfaction-hnn`

## Inline syntax

```text
<emotion:sad>
<style:whisper:2>
<speed:slower>
<Laughter:2>
<restore>
<restore:2>
<restore:1@2>
```

Iterations are 1–5. Start with 1; use 1–2 for subtle edits. More iterations can degrade identity. Processing order is emotion, style, speed, paralinguistic placement, then restoration.

Native ChatterBox 23-language tokens such as `<laughter>` differ from Step post-processing tags such as `<Laughter:2>`; the colon identifies the Step form. Prefer the Step route for consistent selective edits.
