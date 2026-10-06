<div align="center">

# ASTRA

**Command a carrier in a war that thinks for itself.**

[![Release](https://img.shields.io/github/v/release/beltromatti/ASTRA?include_prereleases&label=release&color=4aa3ff)](https://github.com/beltromatti/ASTRA/releases)
[![Status](https://img.shields.io/badge/status-alpha-f59e0b)](#status)
[![Unreal Engine 5.8](https://img.shields.io/badge/Unreal%20Engine-5.8-313131?logo=unrealengine&logoColor=white)](https://www.unrealengine.com)
[![macOS](https://img.shields.io/badge/macOS-Apple%20Silicon-111111?logo=apple&logoColor=white)](#play-the-alpha)
[![Windows](https://img.shields.io/badge/Windows-build%20from%20source-0078D6?logo=windows&logoColor=white)](#windows)
[![Python 3.13](https://img.shields.io/badge/mind-Python%203.13-3776AB?logo=python&logoColor=white)](mind/)
[![LLMs via OpenRouter](https://img.shields.io/badge/LLMs-OpenRouter-6E56CF)](https://openrouter.ai)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)

![The ASN Aquila over New Ravenna](docs/media/hero.jpg)

</div>

ASTRA is a first-person space war game in which every person you meet has a mind of their own. You are the Captain of the ASN Aquila,
a carrier of the 7th Fleet, at the Janus Gate of the Aurelia March, and the Kharon Mandate is coming through. You give your orders out
loud, in your own language. Your officers answer, act, tell you what they did and tell you when they think you are wrong. Allied captains
fight beside you with their own judgment. Enemy commanders call you on an open channel. A high command moves real fleets on a real map,
and the war goes on whether you are winning it or not.

It is a concept of where games are heading: a simulated world that runs by itself, and characters who live in it in real time, as people
rather than scripts.

ASTRA is designed and built by **Mattia Beltrami**, a Computer Engineering student at Politecnico di Milano.

## What it is like

**You speak, they act.** Hold the talk key and say what you would say on a real bridge: "Helm, come about to two-seven-zero, all ahead
full." "Voss, rails on the Acheron, keep firing until her shields drop." "Price, launch Alpha, cover the Praetorian." The ship turns,
the guns open up, the Falcons go down the catapult, and each officer reports back in a sentence. Say it in Italian, Spanish, French,
German, Portuguese, Dutch or English: the bridge answers in the language you use.

**The war does not wait.** Vice Admiral Rourke gives you orders from the 7th Fleet and changes them when the war changes. The Mandate's
high command plans its own campaign against the March. Your allies talk on the fleet net and make their own calls. A Mandate commander
can open a channel to bargain, to threaten, or to buy time, and you can answer him in your own words.

**A ship to walk.** Leave the chair and the Aquila is yours: twelve decks, lifts, the mess hall, the medbay with the wounded of your last
fight, Main Engineering, the flight deck. Climb into a Falcon and fly it yourself.

**Battles with weight.** Railguns at thirty kilometres, lasers up close, missile salvos against point defence, shields that hold until
they do not. Fires and hull breaches below decks, ships that break apart a section at a time. The fallen stay fallen, and the Aquila can
be lost.

**A story that comes from what happened.** A director reads the war and what you did in it, and when a battle decides something, a
narrator tells the end of the chapter on a black screen, in your language.

## Screenshots

<table>
  <tr>
    <td><img src="docs/media/battle.jpg" alt="A Mandate carrier burning under the 7th Fleet's fire"/></td>
    <td><img src="docs/media/bridge.jpg" alt="The bridge of the Aquila, the crew at their stations"/></td>
  </tr>
  <tr>
    <td><img src="docs/media/under_fire.jpg" alt="The Aquila under fire, lasers and rails crossing"/></td>
    <td><img src="docs/media/battle_line.jpg" alt="A Praetorian of the 7th Fleet in the battle line"/></td>
  </tr>
  <tr>
    <td><img src="docs/media/gate.jpg" alt="The Janus Gate over New Ravenna"/></td>
    <td><img src="docs/media/flight_deck.jpg" alt="Alpha's Falcons in their bays on the flight deck"/></td>
  </tr>
  <tr>
    <td><img src="docs/media/stations.jpg" alt="Helm and tactical, the holo table between them"/></td>
    <td><img src="docs/media/holo.jpg" alt="The holo table: the war at a glance"/></td>
  </tr>
  <tr>
    <td><img src="docs/media/fleet.jpg" alt="The ASN Vigilant of the 7th Fleet"/></td>
    <td><img src="docs/media/corridor.jpg" alt="Corridor 1-A behind the bridge"/></td>
  </tr>
</table>

<p align="center"><img src="docs/media/intro.jpg" width="70%" alt="The introduction, narrated and subtitled in the player's language"/></p>


### A new watch: alpha 0.1.1

<table>
  <tr><td><img src="docs/media/reactor_blast.jpg" alt="A reactor breach, fragments and the shock front above New Ravenna"/></td><td><img src="docs/media/close_exchange.jpg" alt="The Aquila firing across a close exchange"/></td></tr>
  <tr><td><img src="docs/media/fleet_war.jpg" alt="The Seventh Fleet battle line"/></td><td><img src="docs/media/aquila_war.jpg" alt="The Aquila in a fleet battle"/></td></tr>
  <tr><td><img src="docs/media/falcon_cockpit.jpg" alt="The actual view from the Captain's Falcon cockpit"/></td><td><img src="docs/media/falcon_wing.jpg" alt="Eagle with the two Falcons on the Captain's wing"/></td></tr>
  <tr><td><img src="docs/media/mandate_war.jpg" alt="An Acheron of the Kharon Mandate"/></td><td><img src="docs/media/hull_damage.jpg" alt="Damage and fires on a Mandate warship"/></td></tr>
  <tr><td><img src="docs/media/kestrel_bay.jpg" alt="The two Kestrels in the assault-shuttle bay"/></td><td><img src="docs/media/bridge_watch.jpg" alt="A watch on the Aquila's bridge"/></td></tr>
</table>

[Visit ASTRA](https://astra.noesisai.it) for the in-game films and the newest available download.

## Play the alpha

**macOS** (Apple Silicon, macOS 14 Sonoma or later, 16 GB of memory recommended): download
`ASTRA-0.1.1-alpha-macOS-AppleSilicon.zip` from the [0.1.1-alpha release](https://github.com/beltromatti/ASTRA/releases/tag/v0.1.1-alpha), unzip it, move
**ASTRA** to Applications and open it. This Shipping app is signed with the developer's Apple Developer ID, notarized by Apple and carries
a stapled notarization ticket. The [website download](https://astra.noesisai.it/download) always selects the newest available Mac release,
including alphas. The original 0.1.0-alpha stays available in the release history.

<a id="windows"></a>**Windows** is the main platform for players, and the project builds for it, but a Windows build has to be made on a
Windows PC (Unreal Engine cannot build Windows from a Mac). With Unreal Engine 5.8.3 and Visual Studio 2022 installed, one command makes
the package: see [Building on Windows](#building-on-windows). There is no prebuilt Windows executable yet, and Windows runtime validation
still requires that PC.

What you need:

- **An OpenRouter API key** ([openrouter.ai/keys](https://openrouter.ai/keys)) with a little credit. The crew's minds think with fast,
  inexpensive language models; the game asks for the key on its first start, checks it and its credit, and tells you if either runs out.
- **A one-time download** on the first start, about 3 GB: the crew's voices and hearing run on your own machine, in seven languages.
  Only the thinking goes to the language models.
- **A microphone** is optional: press T to type an order instead.

The introduction at the start of your first campaign shows the bridge, the ship and the war in two minutes (Space skips a shot, Esc skips
it all). Hold Q for equipment; K shows every control (F1 also works on PC); SETTINGS has graphics, sound, language, the keys and your AI key.

## How it works

```
 Unreal Engine 5.8 (C++)                                   the mind (Python 3.13)
 ┌────────────────────────────────┐   WebSocket, JSON   ┌────────────────────────────────────────────┐
 │ the ship, the war simulation,  │ ◀─────────────────▶ │ crew agents with the ship's real tools     │
 │ damage, sensors, flight,       │   ship state ▶      │ the speech stage: who speaks, when         │
 │ boarding, interiors, screens   │   ◀ orders, lines   │ war minds: high commands, captains, enemy  │
 │ voice playback, subtitles      │   ◀ voice (PCM)     │ the director and the narrator              │
 └────────────────────────────────┘                     └───────┬──────────────────────┬─────────────┘
                                                                 │                      │
                                                    local voices and hearing     language models
                                                  (Pocket TTS, Parakeet, Whisper)  via OpenRouter
```

- **The game** simulates everything that can be simulated: ballistics, shields by face, damage by hull section, fires and breaches,
  sensors and emissions control, flight groups, boarding parties, the fleets of a whole star system. It hands the mind a picture of the
  ship many times a second and carries out what the minds decide.
- **The mind** is a Python service the game starts by itself. Every officer is an agent with a persona, a memory and the ship's tools
  (helm, weapons, sensors, communications, flight, damage control). A speech stage decides who has the floor, so the Captain is never
  talked over and nothing said to him is lost. The war minds plan with the same map the game simulates, and a director keeps the story
  moving.
- **Voices and listening run locally**: Pocket TTS by Kyutai for seven languages, Parakeet on the Apple Neural Engine (Whisper and ONNX
  on other machines). The crew thinks with DeepSeek through OpenRouter, with fallbacks when a model is slow.
- **One rule above all**: the characters' intelligence lives in their prompts, in what they can see and in the tools they can use. No
  code filters what a model says.

## Building from source

You need Unreal Engine 5.8.3, [uv](https://docs.astral.sh/uv/) and git with git-lfs. The full steps are in
[CONTRIBUTING.md](CONTRIBUTING.md); in short:

```bash
git lfs install
git clone https://github.com/beltromatti/ASTRA.git
cd ASTRA && cp .env.example .env    # then put your OpenRouter key in .env
tools/setup_epic_content.sh         # Epic's mannequins, copied from your engine
```

Open `ASTRA.uproject`, let Unreal build the module, and play `L_Bridge`. The game starts the crew's mind on its own.

### Building on Windows

On a PC with Unreal Engine 5.8.3 and Visual Studio 2022:

```powershell
tools\windows\Setup-EpicContent.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tools\windows\Pacchetto-Windows.ps1 -Config Shipping -Zip
```

The package comes with uv and the crew's sources inside, asks for the OpenRouter key on its first start, and keeps the crew's data in
`%LOCALAPPDATA%\ASTRA`. [docs/WINDOWS.md](docs/WINDOWS.md) has the details.

## Status

This is an **alpha**: a complete, playable slice of the idea, with rough edges. A campaign at the Janus Gate, the whole of the Aquila
inside, the war of the Aurelia March around her, the loss of the ship and what comes after, a narrated end of each chapter.

What is next: people who look like people (the crew is still made of Unreal's mannequins), more ships, the planet surface, Windows
releases, multiplayer. The design documents are in [docs/](docs/) (mostly in Italian, with English names), the current state of the work
in [docs/STATO.md](docs/STATO.md).

## Credits and licence

ASTRA's code and its own assets are released under the [MIT licence](LICENSE). It is built with Unreal Engine and on the generous work of
many others, credited in [CREDITS.md](CREDITS.md): third-party content keeps its own licence, and content made from Unreal Engine templates
and the Epic mannequin may only be used with Unreal Engine.
