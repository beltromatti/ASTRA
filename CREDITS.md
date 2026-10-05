# Credits

ASTRA is designed and built by **Mattia Beltrami**. It stands on the work of many people who share theirs. Everything below keeps its own
licence; the line-by-line register, with every change made, is [docs/licenze.csv](docs/licenze.csv).

## Engine and runtime

- **Unreal Engine 5.8** by Epic Games, under the Unreal Engine EULA. The first-person template's blueprints (`Content/FirstPerson`) and the
  Captain's first-person arms (`Content/ASTRA/Weapons/SKM_ASTRA_Arms`, cut from Epic's Manny mannequin) are Epic content under the same
  EULA: use them only with Unreal Engine.
- **uv** by Astral Software Inc. (MIT or Apache-2.0): it builds the crew's Python environment on the first start and travels inside the game.
- The crew's language models run through **OpenRouter**; no model is shipped with the game.

## Voices and listening

- **Pocket TTS** by Kyutai: the code under MIT, the weights and the voices under CC BY 4.0 (huggingface.co/kyutai/pocket-tts).
- **Parakeet TDT 0.6B v3** by NVIDIA (CC BY 4.0) and **Parakeet Ultra** by Moondream (CC BY 4.0): speech recognition. The ONNX export for
  CPUs is by k2-fsa (sherpa-onnx, Apache-2.0).
- **FluidAudio** and **text-processing-rs** by FluidInference (Apache-2.0): Parakeet on the Apple Neural Engine.
- **WhisperKit** by Argmax with **Whisper large-v3-turbo** by OpenAI (MIT), and **faster-whisper** by SYSTRAN (MIT): the fallback recognisers.
- **lingua** by Peter M. Stahl (Apache-2.0), **num2words** by Savoir-faire Linux and Taro Ogawa (LGPL-2.1), **SciPy** (BSD-3-Clause).

## Art

- **Deep Star Maps 2020**: NASA/GSFC Scientific Visualization Studio, with Gaia DR2 data by ESA/Gaia/DPAC (svs.gsfc.nasa.gov/4851). The sky
  of the Aurelia system is made from it. Its use does not imply any endorsement by NASA.
- PBR materials by **ambientCG** (Lennart Demes, CC0): plastics, metals, walkways, rubber, fabrics, leathers, woods, carpets, tiles,
  terrazzo, plaster, cork, rock, grass, moss, ground and snow.
- Plants by **Poly Haven** (CC0): Syngonium, Pachira, Fern, Calathea and Anthurium by Rob Tuytel and Rico Cilliers; Haworthia by James Ray Cock.
- **AR-181** by Frostoise (CC BY 4.0, sketchfab.com/3d-models/ar-181-f32fe06215434fb2a159d29343079a1e): the marines' rifle.
- **M27S Automatic pistol** by Tuuttipingu (CC BY 4.0, sketchfab.com/3d-models/m27s-automatic-pistol-ddc4ae5924ab4eb197f16e43a4d94389): the
  Captain's sidearm.
- Fonts: **Barlow Condensed** by The Barlow Project Authors and **IBM Plex Mono and Sans** by IBM Corp. (SIL Open Font License 1.1).

## Music and sound

- The score is rendered from **VSCO 2 Community Edition** by Versilian Studios (CC0) with `tools/music/score.py`.
- Every sound effect is synthesized by ASTRA's own tools.

## The rest

The ships, the stations, the planet, the interiors, the war, the story, the characters and the code are ASTRA's own (MIT, see
[LICENSE](LICENSE)), made with Blender, Unreal Engine and a great deal of patience.
