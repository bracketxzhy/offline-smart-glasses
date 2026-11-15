# ECE 1110 Course Project Complete Plan
## Offline Smart Glasses with Split Sensing and Edge AI Computing on Raspberry Pi

> **Course:** ECE 1110 Computer Organization and Architecture  
> **Team size:** 4  
> **Proposal deadline:** Next Monday  
> **Budget:** ≤ CNY 2,000 total (≤ CNY 500/person)  
> **Target form:** A genuinely wearable prototype  
> **Core requirement:** Entire runtime works offline; Internet is allowed only for development, downloading models, and installation.

---

# 1. Project Definition

## 1.1 Proposed title

**Design and Evaluation of an Offline Edge-AI Smart Glasses Architecture on Raspberry Pi**

Alternative shorter title:

**Offline Smart Glasses with Split Sensing and Edge AI Computing**

The first title is recommended because it makes the **computer architecture and evaluation focus** explicit instead of making the project look like only an embedded AI demo.

---

## 1.2 Core idea

The project builds a pair of wearable smart glasses containing a camera and microphone. The glasses are connected by cable to a pocket-sized computing and battery module built around a Raspberry Pi 5.

The glasses continuously capture low-frame-rate visual information. The Raspberry Pi processes the camera stream locally and performs:

1. **Face recognition** for registered users.
2. **Object and scene recognition**.
3. **Visual question answering** using a small local VLM.
4. **Natural voice interaction** through a wake word and offline speech recognition.
5. **Audio output** through wired earphones as the primary interaction method.

The system does **not** require Internet access during use.

The project is not only intended to build a working wearable system. Its main academic objective is to evaluate how different on-device AI architectures affect:

- latency,
- CPU cycles,
- instructions,
- CPI / IPC,
- cache behavior,
- memory consumption,
- power consumption,
- temperature,
- task accuracy.

---

# 2. Why This Project Fits ECE 1110

The course project specification explicitly allows a self-designed project related to computer architecture and states that the project should involve:

- hardware,
- simulation,
- application,
- performance comparison.

This project addresses all four.

| Course requirement | This project |
|---|---|
| Hardware | Raspberry Pi 5, camera, microphone, battery, earphone, wearable frame |
| Simulation | Pipeline-level edge inference performance simulator |
| Application | Offline smart glasses with visual recognition and voice interaction |
| Performance comparison | VLM-only vs modular vs adaptive inference architectures |
| Computer architecture | CPU execution, memory hierarchy, cache misses, CPI/IPC, power and thermal behavior |

The main architectural question is therefore:

> **Can a modular and adaptive edge-AI architecture provide lower latency and energy consumption than a VLM-only architecture for fully offline smart glasses on a Raspberry Pi while maintaining sufficient task accuracy?**

This will be the central research question for the whole project.

---

# 3. Related Work: OpenGlass

The main reference system is:

**OpenSQZ/OpenGlass**  
https://github.com/OpenSQZ/OpenGlass

OpenGlass is an open research platform for wearable sensing and nearby-device local multimodal inference.

Its main design concept is a **sensing-computing split architecture**:

```text
Wearable device
    │
    ├── Camera
    └── Microphone
    │
    ▼
Nearby computing host
    │
    ├── ASR
    ├── VLM / MLLM
    ├── LLM
    └── TTS
```

In OpenGlass, the wearable sensing unit uses an ESP32-S3 and sends image/audio data to a nearby laptop or edge host. The large model does not run on the glasses.

The current public experimental OpenGlass multimodal runtime primarily assumes a much more powerful nearby computer, including an NVIDIA GPU for the MiniCPM-o path.

Our project keeps the split-computing idea but changes the computing architecture:

```text
OpenGlass

ESP32-S3 glasses
       │
     Wi-Fi
       │
       ▼
Laptop / GPU host
```

versus:

```text
Our Project

Wearable camera + microphone
       │
      USB
       │
       ▼
Raspberry Pi 5 + battery
       │
    user's pocket
```

The key difference is that our computing platform is much more constrained in:

- CPU throughput,
- memory bandwidth,
- RAM capacity,
- power budget,
- thermal budget.

Therefore, this project is not simply a reproduction of OpenGlass. It investigates how the same general concept can be redesigned for a **fully portable ARM edge computer**.

---

# 4. Design Principles

The project should follow four principles.

## 4.1 Keep the glasses lightweight

The glasses should only contain the parts that must physically stay near the user's eyes:

- camera,
- microphone,
- optional status LED / button,
- mechanical frame.

The following should remain in the pocket module:

- Raspberry Pi,
- battery,
- cooling,
- storage,
- AI inference.

This prevents excessive glasses weight and makes the prototype genuinely wearable.

---

## 4.2 Do not run the VLM continuously

Running a VLM continuously on Raspberry Pi is inefficient.

The camera may operate continuously at a low frame rate, but different AI workloads should run at different frequencies.

Recommended design:

```text
Camera stream:                1–3 FPS
Face detector:                1–2 FPS
Object detector:              1–2 FPS
Face recognition embedding:   only when a face is detected
VLM:                          only when requested by the user
LLM:                          only when required
```

The VLM should be **event-driven**, not frame-driven.

This distinction is critical for both performance and power.

---

## 4.3 Use specialized models for simple tasks

Do not send every problem to the VLM.

Example:

### Bad architecture

```text
Camera
  ↓
VLM
  ↓
Answer
```

This is simple but unnecessarily expensive.

### Better architecture

```text
                    ┌── Face recognition
Camera → Router ────┼── Object detection
                    └── VLM
                           │
                           ▼
                     Small LLM
```

Simple tasks use smaller models.

Complex visual questions use the VLM.

---

## 4.4 Architecture must be measurable

Every important subsystem should expose timing and resource data.

Each request should generate a log such as:

```text
timestamp
task_type
capture_time_ms
preprocess_time_ms
detector_time_ms
vlm_time_ms
llm_time_ms
tts_time_ms
total_latency_ms
memory_peak_mb
cpu_usage
temperature
energy_estimate
```

This makes the project scientifically evaluable rather than just demonstrable.

---

# 5. Final System Architecture

## 5.1 Physical architecture

```text
┌─────────────────────────────────────┐
│            SMART GLASSES            │
│                                     │
│  Camera                             │
│  Microphone                         │
│  Wake-word audio input              │
│  Optional status LED / button       │
└──────────────────┬──────────────────┘
                   │
                USB cable
                   │
                   ▼
┌─────────────────────────────────────┐
│          POCKET COMPUTE UNIT        │
│                                     │
│  Raspberry Pi 5 8 GB                │
│  Active cooler                      │
│  microSD / SSD                      │
│  Local AI models                    │
│  Local face database                │
│                                     │
└──────────────────┬──────────────────┘
                   │
            USB-C power input
                   │
                   ▼
               Power bank

                   │
                   ▼
            Wired earphones
```

---

# 6. Interaction Design

## 6.1 Continuous visual sensing

The camera remains active while the device is in use.

Recommended initial configuration:

- resolution: **640×480** or **640×360**
- capture rate: **2 FPS**
- detector rate: **1–2 FPS**

Reason:

- smart glasses do not need 30 FPS for face identification;
- Raspberry Pi inference is resource constrained;
- lower FPS reduces memory traffic, CPU load and power.

---

## 6.2 Voice wake-up

The complete version should support:

```text
User:
"Hey Glass"

       ↓

Wake-word detector

       ↓

Offline ASR

       ↓

Intent / query classification

       ↓

AI pipeline

       ↓

Answer
```

The wake-word detector should continuously listen using a lightweight model.

The full ASR model should only start after the wake word is detected.

---

## 6.3 Example interactions

### Example A: Face recognition

User:

> "Hey Glass, who is this?"

System:

```text
Camera
 ↓
Face detector
 ↓
Face embedding
 ↓
Local face database
 ↓
Identity match
 ↓
Local information retrieval
 ↓
TTS
```

Response:

> "This is Alice Zhang, an electrical engineering student."

---

### Example B: Object recognition

User:

> "Hey Glass, what is in front of me?"

System:

```text
Camera
 ↓
Object detector
 ↓
Detected objects
 ↓
Small LLM or template
 ↓
TTS
```

Response:

> "There is a laptop, a bottle, and one person in front of you."

---

### Example C: Complex visual question

User:

> "Hey Glass, what is the person holding?"

System:

```text
Camera
 ↓
VLM
 ↓
Answer
 ↓
TTS
```

The VLM is activated only here.

---

# 7. Output Method Decision

## 7.1 Recommended choice: wired earphones

The primary output should be **audio through wired earphones**.

Reasons:

1. Very low hardware complexity.
2. Very low cost.
3. No optical alignment problem.
4. Easy to demonstrate.
5. Leaves the project budget for computation and sensing hardware.
6. Better matches the voice interaction architecture.

---

## 7.2 Why a display is not part of the core MVP

A proper near-eye display is not equivalent to attaching a cheap OLED to glasses.

A usable HUD introduces:

- optics,
- focal distance,
- eye relief,
- combiner / prism,
- brightness,
- mechanical alignment,
- weight balance,
- display driver,
- additional power consumption.

A cheap OLED is inexpensive but generally does not provide a useful see-through near-eye display.

Therefore:

> **Audio is the required output path. A display is a stretch goal only if a suitable near-eye module is found within the remaining budget.**

Do not let the display become a dependency for project completion.

---

# 8. Hardware Selection

## 8.1 Raspberry Pi

### Recommended:

**Raspberry Pi 5, 8 GB RAM**

Relevant architecture:

- Broadcom BCM2712
- 4 × Arm Cortex-A76
- 2.4 GHz
- shared L3 cache
- LPDDR4X memory
- USB 3.0
- dual MIPI camera/display interfaces
- USB-C 5 V / 5 A power

The 8 GB configuration is preferred because:

- 4 GB is unnecessarily restrictive for VLM experimentation;
- 8 GB leaves enough memory for the OS plus a 1–3B quantized model;
- 16 GB increases the price significantly but does not increase CPU compute performance.

For this project, **8 GB is the correct balance**.

---

# 9. Proposed Hardware BOM

Prices are planning estimates rather than guaranteed purchase prices.

| Component | Target specification | Estimated cost (CNY) |
|---|---|---:|
| Raspberry Pi 5 8 GB | main compute platform | 650–800 |
| Raspberry Pi active cooler | mandatory | 35–60 |
| microSD 128 GB | A2 preferred | 60–100 |
| USB camera module | compact 720p/1080p | 60–150 |
| USB / I2S microphone | compact | 30–80 |
| Power bank | USB-C PD, ≥20 W, preferably 10,000 mAh | 100–180 |
| USB-C cable | short high-current cable | 20–40 |
| Wired earphone | 3.5 mm/USB or existing one | 0–80 |
| USB audio adapter if needed | microphone/output support | 20–50 |
| 3D printed glasses frame | outsourced | 80–200 |
| Wiring / screws / adhesive | miscellaneous | 30–80 |
| USB power meter | voltage/current/power logging | 40–100 |
| **Estimated total** |  | **1,125–1,920** |

Target purchase total:

> **CNY 1,500–1,800**

This leaves a small margin under the CNY 2,000 budget.

---

# 10. Mechanical Design

The glasses should not carry the Raspberry Pi or battery.

## Components mounted on glasses

- compact camera;
- microphone;
- optional button;
- cable strain relief.

## Pocket unit

Use a simple ventilated Raspberry Pi enclosure containing:

- Pi 5,
- active cooler,
- storage,
- USB connections.

Battery should be separate or attached externally to the pocket module.

---

# 11. Software Architecture

```text
┌───────────────────────┐
│ Camera Capture Thread │
└──────────┬────────────┘
           ▼
┌───────────────────────┐
│ Shared Frame Buffer   │
└──────────┬────────────┘
           │
       ┌───┴───────────────┐
       │                   │
       ▼                   ▼
Face Detection       Object Detection
       │                   │
       ▼                   │
Face Embedding             │
       │                   │
       ▼                   │
Face Database              │
       └──────┬────────────┘
              ▼
       Context Database

Microphone
    │
    ▼
Wake Word
    │
    ▼
Offline ASR
    │
    ▼
Intent Router
    │
    ├── identity → face pipeline
    ├── object   → detector
    └── complex  → VLM
                     │
                     ▼
                  Answer
                     │
                     ▼
                 Offline TTS
                     │
                     ▼
                  Earphone
```

---

# 12. Model Architecture

The project should not lock itself to a single large model.

## 12.1 Face detection

Candidate classes:

- lightweight YOLO face detector;
- SCRFD;
- another small ONNX face detector.

Primary metric:

- detection accuracy,
- latency.

---

## 12.2 Face embedding

Candidate:

- MobileFaceNet,
- ArcFace-compatible lightweight network.

Operation:

```text
face image
   ↓
embedding vector
   ↓
cosine similarity
   ↓
registered identity / unknown
```

Database should store:

```text
person_id
name
role_or_major
short_note
embedding
```

Recommended initial database:

> **10–30 consenting registered people**

Unknown faces return:

> **Unknown person**

---

# 13. Object Detection

Use a small model such as a nano-class detector.

The purpose is not to maximize benchmark accuracy.

The purpose is to provide a fast architecture path for questions such as:

- What objects are in front of me?
- Is there a laptop?
- How many people are in front of me?

This model will be compared directly with the VLM path.

---

# 14. Local LLM

Use a quantized small language model.

Recommended model scale:

> **approximately 1–3B parameters**

Recommended runtime:

**llama.cpp**

Use a 4-bit quantized model for the final benchmark unless a different quantization is part of an explicit experiment.

Raspberry Pi 5 measurements published by independent projects show that small 2–3B quantized models can run at several tokens per second on the Cortex-A76 CPU. This makes short-response generation practical, while larger models quickly become too slow or memory-intensive for interactive wearable use.

The LLM should not generate long answers.

Recommended response length:

> **1–2 short sentences**

---

# 15. VLM

A small VLM is required by project scope.

Recommended size:

> **approximately 0.5–2.2B**

Candidate family:

- SmolVLM / SmolVLM2 class,
- another llama.cpp-compatible small multimodal model that is confirmed to run on Arm64.

The final VLM should be selected through an early **model feasibility benchmark**, not by model popularity.

Required VLM test before integration:

| Test | Requirement |
|---|---|
| Model loads on Pi 5 8 GB | required |
| Single 640p image accepted | required |
| Short answer generated | required |
| Peak RAM < practical system limit | required |
| No thermal crash / OOM | required |
| Response latency measurable | required |

The VLM does not need to be fast enough for continuous video.

It only needs to be fast enough for **on-demand visual questions**.

---

# 16. Offline Speech Recognition

Recommended approach:

```text
Wake word
    ↓
audio recording
    ↓
local ASR
    ↓
query text
```

Possible ASR class:

- whisper.cpp with a small/tiny model;
- another lightweight offline speech recognizer.

Speech recognition does not run continuously.

Only the wake-word engine runs continuously.

---

# 17. Offline TTS

Use a lightweight offline TTS engine.

The exact voice quality is secondary.

Evaluation should focus on:

- output start latency,
- total response latency,
- CPU utilization.

---

# 18. Intent Router

The router determines which compute path to use.

Example:

```text
"Who is this?"
→ FACE

"What is in front of me?"
→ OBJECT

"How many people are here?"
→ OBJECT

"What is the person holding?"
→ VLM

"Describe what is happening."
→ VLM
```

The first version should use **rule-based intent classification**, not another AI model.

Example:

```python
if identity_keywords:
    mode = "FACE"
elif object_keywords:
    mode = "OBJECT"
else:
    mode = "VLM"
```

This keeps routing latency nearly negligible.

---

# 19. Three Architectures to Compare

This comparison is the academic core of the project.

---

## Architecture A — VLM-only

```text
Camera
 ↓
VLM
 ↓
Answer
```

Advantages:

- simplest software design;
- high flexibility.

Disadvantages expected:

- high latency;
- high RAM;
- high energy;
- unnecessary computation for easy questions.

---

## Architecture B — Modular

```text
Camera
 ↓
Task-specific model
 ↓
Face / object result
 ↓
small LLM / template
 ↓
Answer
```

Advantages expected:

- low latency for simple tasks;
- lower resource usage.

Disadvantage:

- less flexible.

---

## Architecture C — Adaptive Hybrid

```text
User question
     ↓
Intent router
     ↓
┌───────────────┬───────────────┬───────────────┐
Face recognition Object detection       VLM
└───────────────┴───────────────┴───────────────┘
                       ↓
                     Answer
```

This is the **proposed architecture**.

The project should not claim that Architecture C is better until measurements confirm it.

---

# 20. Main Hypothesis

The proposal may state the hypothesis as:

> For common smart-glasses tasks, a task-adaptive architecture will reduce end-to-end latency, memory traffic, CPU work, and energy per query compared with routing every request through a VLM, while retaining VLM flexibility for complex questions.

This is a testable hypothesis.

---

# 21. Performance Metrics

## 21.1 User-level metrics

### End-to-end latency

\[
T_{total}
=
T_{capture}
+
T_{ASR}
+
T_{routing}
+
T_{vision}
+
T_{LLM}
+
T_{TTS}
\]

Measure:

- mean,
- median,
- P95.

---

## 21.2 Computer architecture metrics

Use Linux `perf`.

Important metrics:

```text
cycles
instructions
cache-references
cache-misses
branches
branch-misses
context-switches
```

Derived metric:

\[
IPC = \frac{Instructions}{Cycles}
\]

and:

\[
CPI = \frac{Cycles}{Instructions}
\]

This directly connects the project to ECE 1110 performance analysis.

---

## 21.3 Memory

Measure:

- resident set size,
- peak RSS,
- swap usage,
- model file size.

---

## 21.4 Thermal

Record:

```bash
vcgencmd measure_temp
```

Measure:

- idle temperature;
- average inference temperature;
- maximum temperature.

Also record throttling status.

---

## 21.5 Power

Use a USB power meter.

Metrics:

- idle power,
- camera-only power,
- detector power,
- VLM power,
- complete query power.

Estimate energy per request:

\[
E = \int P(t)\,dt
\]

If power is approximated as constant during a task:

\[
E \approx P_{avg} T
\]

Report in Joules/query.

---

# 22. Accuracy Metrics

## Face recognition

Measure:

- known-person accuracy,
- unknown rejection accuracy,
- false acceptance,
- false rejection.

---

## Object detection

For the project benchmark, use task-level correctness rather than training a full detection benchmark from scratch.

Example:

```text
Question:
"Is there a laptop?"

Correct / Incorrect
```

---

## VLM

Prepare a fixed set of visual questions with manually verified answers.

Score:

- correct;
- partially correct;
- incorrect.

The scoring rubric must be defined before experiments.

---

# 23. Benchmark Dataset

Create a small but controlled project dataset.

## 23.1 Face dataset

Target:

- 10 registered participants;
- 10–20 evaluation images per participant;
- different angle / distance / lighting;
- separate unknown people.

Target size:

> approximately 150–250 images.

---

## 23.2 Object / scene dataset

Target:

> approximately 50 scenes.

Objects can include:

- laptop,
- bottle,
- phone,
- chair,
- backpack,
- person,
- book.

---

## 23.3 Visual question dataset

Target:

> 30–50 image-question pairs.

Categories:

1. object presence,
2. object count,
3. spatial relationship,
4. human action,
5. complex scene description.

---

# 24. Experimental Protocol

Every architecture should be tested under the same conditions.

Control variables:

- same Raspberry Pi;
- same cooling;
- same image;
- same image resolution;
- same question;
- same model version;
- same CPU frequency policy;
- same quantization;
- same room-temperature range when practical.

Before benchmarking:

1. reboot;
2. wait for background activity to settle;
3. confirm temperature;
4. check throttling status;
5. run warm-up;
6. begin measurements.

Run each benchmark multiple times.

Recommended:

> **at least 10 repetitions per latency condition**

---

# 25. Main Experiment

For simple queries:

```text
Architecture A: VLM-only
Architecture B: modular
Architecture C: adaptive
```

Measure:

| Metric | A | B | C |
|---|---:|---:|---:|
| Accuracy | | | |
| Median latency | | | |
| P95 latency | | | |
| CPU cycles | | | |
| Instructions | | | |
| CPI | | | |
| Cache misses | | | |
| Peak RAM | | | |
| Avg. power | | | |
| Energy/query | | | |
| Max temperature | | | |

This table should appear in the final report.

---

# 26. Quantization Experiment

If time allows, evaluate one model under at least two quantization settings.

Example:

```text
Q4
vs
Q8
```

Measure:

- model size,
- RAM,
- latency,
- accuracy,
- energy.

This gives a clear architecture trade-off:

> precision / model size / memory traffic / execution speed.

---

# 27. Resolution Experiment

Test:

```text
320×240
640×480
1280×720
```

Measure:

- detector latency,
- VLM latency,
- accuracy,
- memory,
- power.

This provides another clean hardware/software trade-off.

---

# 28. Camera Frame-Rate Experiment

Test continuous operation at:

```text
1 FPS
2 FPS
5 FPS
```

Measure:

- CPU usage,
- power,
- temperature,
- recognition responsiveness.

Expected final setting:

> approximately **2 FPS**

but this must be confirmed experimentally.

---

# 29. Simulation

The course specification asks for simulation, so the project should include a simple **edge inference pipeline simulator**.

Do not build a full CPU simulator.

The simulator should model the system as sequential or conditionally activated stages.

Example:

```text
Camera
  ↓
ASR
  ↓
Router
  ↓
Detector / VLM
  ↓
LLM
  ↓
TTS
```

Each stage has:

```text
latency
power
probability of activation
```

---

# 30. Simulation Model

For path \(p\):

\[
T_p = \sum_i T_i
\]

Expected system latency:

\[
E[T] = \sum_p P(p)T_p
\]

Expected energy:

\[
E[E] = \sum_p P(p)\sum_i P_iT_i
\]

where:

- \(P(p)\): probability of choosing path \(p\);
- \(T_i\): stage latency;
- \(P_i\): average stage power.

Example workload:

```text
40% face queries
35% object queries
25% complex VLM queries
```

Compare predicted values with measured results.

Simulation error:

\[
Error_T =
\frac{|T_{sim}-T_{real}|}
     {T_{real}}
\times 100\%
\]

---

# 31. Why the Simulation Matters

The simulator answers questions such as:

- What happens if VLM queries increase from 20% to 60%?
- What happens if the camera runs at 5 FPS instead of 2 FPS?
- What is the estimated battery lifetime?
- Which stage dominates latency?
- Which stage dominates energy consumption?

This provides a meaningful architectural analysis instead of a decorative simulation.

---

# 32. Logging System

Every inference should produce a JSON or CSV record.

Example:

```json
{
  "task": "face",
  "resolution": "640x480",
  "capture_ms": 21.3,
  "asr_ms": 412.2,
  "vision_ms": 97.4,
  "llm_ms": 0,
  "tts_ms": 181.8,
  "total_ms": 712.7,
  "cycles": 0,
  "instructions": 0,
  "cache_misses": 0,
  "memory_peak_mb": 0,
  "temperature_c": 0,
  "power_w": 0
}
```

Do not manually record large numbers of benchmark values.

Build logging from the beginning.

---

# 33. Repository Structure

Recommended repository:

```text
smart-glasses/
│
├── README.md
├── docs/
│   ├── proposal.md
│   ├── architecture.md
│   └── experiment_protocol.md
│
├── hardware/
│   ├── bom.md
│   ├── cad/
│   └── assembly.md
│
├── src/
│   ├── camera/
│   ├── face/
│   ├── object_detection/
│   ├── vlm/
│   ├── asr/
│   ├── wake_word/
│   ├── tts/
│   ├── router/
│   └── main.py
│
├── benchmark/
│   ├── run_benchmark.py
│   ├── perf/
│   └── results/
│
├── simulator/
│   ├── simulator.py
│   └── configs/
│
└── tests/
```

---

# 34. Development Strategy

Do **not** start by assembling the glasses.

Development order must be:

```text
Models work on laptop
      ↓
Models work independently on Pi
      ↓
Architecture integration
      ↓
Benchmark logging
      ↓
Camera + microphone integration
      ↓
Wearable frame
      ↓
Full demo
```

The expensive mistake would be to spend the first two weeks designing the frame while the VLM still has not been demonstrated on the Pi.

---

# 35. Minimum Viable Product (MVP)

The project is considered technically alive once the following works:

```text
Camera
 ↓
Raspberry Pi
 ↓
face or object recognition
 ↓
text response
```

Required MVP functions:

- continuous low-FPS camera;
- face detection;
- registered-person recognition;
- object recognition;
- local execution;
- benchmark logging.

The MVP does **not** require voice interaction.

---

# 36. Full Required Version

The final required system should include:

- wearable frame;
- Raspberry Pi pocket unit;
- battery;
- camera;
- microphone;
- continuous low-FPS sensing;
- local wake word;
- offline ASR;
- face recognition;
- object detection;
- VLM;
- task router;
- offline TTS;
- wired earphone;
- performance logging;
- simulator;
- architecture comparison.

---

# 37. Stretch Goal

Only after the complete required system works:

### Optional near-eye display

Potential use:

```text
Alice Zhang
ECE Student
Confidence: 0.92
```

The display must not replace or delay core experimental work.

---

# 38. Team Division

There are four people and no strong technical preference.

Use subsystem ownership.

## Member A — Hardware / Wearable

Responsible for:

- camera;
- microphone;
- Pi hardware;
- power;
- cooling;
- frame CAD adaptation;
- 3D printing;
- cable management;
- assembly.

---

## Member B — Vision

Responsible for:

- face detection;
- face embeddings;
- local face database;
- object detection;
- image preprocessing.

---

## Member C — Multimodal / Voice

Responsible for:

- VLM;
- local LLM;
- wake word;
- ASR;
- TTS;
- intent router.

---

## Member D — Architecture / Evaluation

Responsible for:

- benchmark scripts;
- `perf`;
- memory measurement;
- power experiment;
- thermal experiment;
- simulator;
- plotting and report data.

---

## Shared responsibilities

All four should participate in:

- integration;
- debugging;
- final demo;
- proposal;
- final presentation.

No member should own an isolated component that nobody else understands.

---

# 39. Proposal Deadline Plan

Proposal deadline is next Monday.

The proposal should be completed before purchasing every component.

## Day 1

Finalize:

- project title;
- research question;
- architecture;
- hardware BOM;
- three comparison architectures.

Output:

```text
proposal outline complete
```

---

## Day 2

Test on existing computer:

- one small object detector;
- one candidate face recognition pipeline;
- one candidate small VLM;
- one small LLM.

Purpose:

> confirm software stack choices before promising exact models.

---

## Day 3

Write:

- Introduction;
- Related Work;
- Proposed Solution;
- Evaluation Method.

Create system architecture figure.

---

## Day 4

Finalize:

- simulation section;
- benchmark metrics;
- expected timeline;
- budget.

---

## Day 5 / Sunday

Review proposal against requirements.

Checklist:

- topic;
- related approaches;
- proposed solution;
- evaluation / proof;
- conclusion.

---

## Monday

Submit proposal.

---

# 40. Suggested Proposal Structure

## 1. Topic

**Design and Evaluation of an Offline Edge-AI Smart Glasses Architecture on Raspberry Pi**

---

## 2. Introduction

Explain:

- smart glasses can provide contextual visual assistance;
- cloud systems introduce network dependency and privacy concerns;
- OpenGlass demonstrates a sensing-computing split;
- existing local MLLM systems often depend on more powerful nearby hosts;
- Raspberry Pi creates a stricter edge-computing problem.

---

## 3. Related Approaches

Cover:

### OpenGlass

- lightweight sensing;
- nearby local inference;
- ESP32-S3 wearable;
- modular ASR/VLM/TTS;
- GPU-capable host in current experimental runtime.

### Conventional VLM-only approach

```text
camera → VLM → answer
```

Strength:

- flexibility.

Weakness:

- computation cost.

### Modular edge AI

```text
camera → task-specific model → answer
```

Strength:

- efficiency.

Weakness:

- lower generality.

---

# 41. Proposed Solution Text

The proposal can use the following technical idea:

> We propose a fully offline smart-glasses architecture consisting of a lightweight wearable sensing unit and a Raspberry Pi 5 pocket computing module. The glasses continuously capture low-frame-rate visual information and audio, while all AI processing is executed locally on the Raspberry Pi. Instead of routing every visual query through a vision-language model, the system uses a task router to select among face recognition, object detection, and VLM inference. Simple and frequent tasks are therefore handled by lightweight specialized models, while the VLM is activated only for questions requiring general visual reasoning.

---

# 42. Evaluation Text

> We will compare three inference architectures: a VLM-only baseline, a modular task-specific pipeline, and our adaptive hybrid architecture. Evaluation will include end-to-end response latency, task accuracy, CPU cycles, instruction count, CPI/IPC, cache misses, memory usage, power consumption, energy per query, and thermal behavior. We will additionally construct a pipeline-level performance simulator and compare simulated latency and energy against measurements from the physical Raspberry Pi system.

---

# 43. Expected Conclusion

Do not promise numerical improvement.

Use:

> We expect the project to demonstrate the feasibility and limitations of fully offline wearable AI on a resource-constrained ARM platform. The evaluation will quantify the trade-offs among model flexibility, latency, memory traffic, power consumption, and accuracy, and determine when specialized edge models are more efficient than general-purpose VLM inference.

---

# 44. Six-Phase Implementation Schedule

The final course deadline has not yet been announced, so use a relative schedule.

## Phase 0 — Proposal

**Now → next Monday**

Deliverables:

- proposal;
- architecture;
- BOM;
- benchmark plan.

---

## Phase 1 — Hardware bring-up

**Week 1 after proposal**

Tasks:

- buy Pi;
- install Raspberry Pi OS 64-bit;
- active cooling;
- power bank;
- camera;
- microphone;
- USB audio;
- test camera stream.

Exit criteria:

```text
Pi stable
camera stable
microphone stable
continuous operation ≥ 1 hour
no thermal throttling
```

---

## Phase 2 — Individual AI models

**Week 2**

Tasks:

- face detection;
- face embedding;
- local face DB;
- object detector;
- LLM;
- VLM feasibility;
- TTS.

Exit criteria:

```text
each module works independently on Pi
```

---

## Phase 3 — Integrated software

**Week 3**

Tasks:

- frame buffer;
- intent router;
- voice pipeline;
- VLM trigger;
- logging;
- API between modules.

Exit criteria:

```text
camera → query → answer
works end to end
```

---

## Phase 4 — Wearable integration

**Week 4**

Tasks:

- 3D printed frame;
- mount camera;
- mount microphone;
- route cable;
- pocket enclosure;
- walking test.

Exit criteria:

```text
wearable for ≥30 min
camera view stable
cable does not detach
```

---

## Phase 5 — Experiments

**Week 5**

Tasks:

- architecture A/B/C;
- perf;
- memory;
- power;
- thermal;
- accuracy;
- simulation.

Exit criteria:

```text
complete results table
```

---

## Phase 6 — Final report and demo

**Week 6**

Tasks:

- figures;
- graphs;
- final conclusions;
- presentation;
- demo script;
- backup recorded demo.

---

# 45. Demo Script

The final live demonstration should be short and deterministic.

## Demo 1 — Known person

A registered teammate stands in front.

User:

> "Hey Glass, who is this?"

Expected:

> name + short information.

---

## Demo 2 — Unknown person

An unregistered person appears.

Expected:

> "Unknown person."

This demonstrates rejection instead of forced classification.

---

## Demo 3 — Object

Place:

- laptop;
- bottle;
- backpack.

Ask:

> "What is in front of me?"

Expected:

> correct object list.

---

## Demo 4 — Complex question

Person holds one object.

Ask:

> "What is the person holding?"

Router should call the VLM.

---

## Demo 5 — Architecture benchmark

Show a small result chart:

```text
VLM-only
vs
Modular
vs
Adaptive
```

This makes the computer architecture contribution visible to the instructor.

---

# 46. Acceptance Criteria

The project should not be declared complete merely because a demo works once.

## Hardware

- [ ] wearable;
- [ ] Pi in pocket;
- [ ] camera physically mounted;
- [ ] microphone physically mounted;
- [ ] battery powered;
- [ ] no Internet required;
- [ ] stable for ≥30 minutes.

## AI

- [ ] known person recognition;
- [ ] unknown rejection;
- [ ] object recognition;
- [ ] VLM query;
- [ ] voice wake-up;
- [ ] offline ASR;
- [ ] TTS.

## Architecture evaluation

- [ ] VLM-only baseline;
- [ ] modular baseline;
- [ ] adaptive design;
- [ ] cycles;
- [ ] instructions;
- [ ] CPI/IPC;
- [ ] cache misses;
- [ ] latency;
- [ ] memory;
- [ ] power;
- [ ] thermal;
- [ ] accuracy.

## Simulation

- [ ] pipeline simulator;
- [ ] real measurements;
- [ ] simulation-vs-real comparison.

---

# 47. Main Risks

## Risk 1 — VLM too slow

This is the most important technical risk.

Control:

- test the VLM before mechanical work;
- use small multimodal models;
- keep answers short;
- call VLM only on demand.

Do not design the entire product around continuous VLM inference.

---

## Risk 2 — Thermal throttling

Pi 5 under sustained inference can become hot.

Control:

- active cooler is mandatory;
- benchmark only after temperature stabilizes;
- log throttling state.

Thermal behavior is also useful experimental data.

---

## Risk 3 — 8 GB memory pressure

Simultaneously keeping ASR, VLM, LLM, detector and other processes loaded may consume substantial RAM.

Architecture should avoid assuming every heavyweight model must actively compute at the same time.

Record peak memory from the beginning.

---

## Risk 4 — Wearability

A prototype can technically work while being unusable to wear.

Control:

- keep Pi and battery off the glasses;
- minimize front weight;
- use strain relief;
- use flexible cable.

---

## Risk 5 — Scope explosion

Do not add:

- navigation,
- cloud synchronization,
- OCR translation,
- facial emotion recognition,
- full conversational memory,
- mapping,
- gesture recognition

before the required architecture comparison is complete.

---

# 48. Privacy and Dataset Rules

Face recognition must use registered people who agree to participate.

Do not collect arbitrary strangers into the face database.

Store:

- embeddings;
- minimal metadata.

Avoid storing unnecessary raw video.

The final report should state:

> The face recognition database contains only voluntarily registered participants and operates entirely on the local device.

---

# 49. What Not to Do

## Do not:

### 1. Put Raspberry Pi on the glasses

It destroys wearability.

### 2. Use 30 FPS just because the camera supports it

This wastes compute and power.

### 3. Send every frame into the VLM

It is incompatible with the resource budget.

### 4. Make the display the central challenge

That shifts the project toward optics/mechanical design rather than computer architecture.

### 5. Only report AI accuracy

The course is computer architecture.

### 6. Only report execution time

Also measure why it takes that time:

- instructions,
- cycles,
- cache misses,
- memory,
- power,
- temperature.

---

# 50. First Purchases After Proposal Approval

Purchase in this order:

1. Raspberry Pi 5 8 GB
2. active cooler
3. 128 GB microSD
4. camera
5. microphone
6. suitable power bank
7. USB power meter
8. cables / USB audio
9. frame materials / 3D printing

Do not pay for a custom near-eye display before the complete Pi inference path has been demonstrated.

---

# 51. First Technical Tests

Immediately after receiving the Pi:

## Test A

```text
camera capture at 640×480 @ 2 FPS
```

Measure:

- CPU,
- memory,
- temperature.

## Test B

Run face detector.

## Test C

Run object detector.

## Test D

Run one 1–3B text LLM.

## Test E

Run candidate VLM on one image.

These five tests determine whether the architecture is realistic.

---

# 52. Early Go/No-Go Checkpoint

At the end of Week 2 answer:

1. Can the Pi load the VLM?
2. What is VLM response latency?
3. Can face detection run continuously?
4. Can the system stay below thermal throttling?
5. Is RAM sufficient?
6. Does battery power remain stable?

If these six questions have measured answers, the project has moved from an idea to an engineering project.

---

# 53. Final Report Structure

Recommended report:

```text
1. Introduction
2. Related Work
3. System Requirements
4. Hardware Architecture
5. Software Architecture
6. Adaptive Inference Design
7. Implementation
8. Simulation Model
9. Experimental Methodology
10. Results
11. Architecture Analysis
12. Limitations
13. Conclusion
```

---

# 54. Key Figures to Prepare

Final report should contain at least:

1. system physical architecture;
2. software pipeline;
3. three compared architectures;
4. wearable prototype photo;
5. latency comparison;
6. energy/query comparison;
7. memory comparison;
8. cache-miss / CPI comparison;
9. accuracy comparison;
10. simulated vs measured latency.

---

# 55. Final Project Success Definition

The project is successful if the team produces:

> A wearable, battery-powered, fully offline smart-glasses prototype that can recognize registered people, identify common objects, answer limited natural visual questions, and respond through voice, together with a controlled architectural evaluation comparing VLM-only, modular, and adaptive inference strategies on Raspberry Pi 5.

The **prototype is the application**.

The **A/B/C comparison is the research experiment**.

The **CPU/memory/power analysis is the computer architecture contribution**.

The **simulator is the model connecting design choices to measured performance**.

These four elements must remain balanced throughout the project.

---

# 56. Current Fixed Decisions

As of the proposal stage, the following decisions are treated as fixed:

- Team size: **4**
- Budget: **≤ CNY 2,000**
- Compute platform: **Raspberry Pi 5 8 GB**
- Device organization: **wearable sensing + pocket compute/battery**
- Runtime: **fully offline**
- Camera: **continuous low-FPS operation**
- Face recognition: **registered local database**
- Voice: **wake word + offline ASR**
- Complex vision: **small local VLM**
- Output: **wired audio as core**
- Display: **stretch goal**
- Architecture comparison:
  - **VLM-only**
  - **modular**
  - **adaptive hybrid**
- Architecture metrics:
  - latency,
  - CPU cycles,
  - instructions,
  - CPI/IPC,
  - cache misses,
  - RAM,
  - power,
  - thermal behavior,
  - accuracy.
- Simulation: **pipeline performance and energy simulator**

---

# 57. Immediate Action List

Before next Monday:

- [ ] Create team repository.
- [ ] Assign A/B/C/D roles.
- [ ] Draw final system architecture diagram.
- [ ] Write proposal Introduction.
- [ ] Write OpenGlass related-work paragraph.
- [ ] Write proposed adaptive architecture.
- [ ] Define A/B/C baseline comparison.
- [ ] Define benchmark metrics.
- [ ] Add simulation method.
- [ ] Add BOM and budget.
- [ ] Add project schedule.
- [ ] Review against the five proposal requirements.
- [ ] Submit proposal.

---

# References

1. OpenSQZ/OpenGlass. *Open research platform for wearable sensing, nearby-device local multimodal inference, and local-first visual assistance.*  
   https://github.com/OpenSQZ/OpenGlass

2. Raspberry Pi Ltd. *Raspberry Pi 5 Specifications.*  
   https://www.raspberrypi.com/products/raspberry-pi-5/

3. ECE 1110 Project Topics Specification. Course-provided document.

4. ECE 1110 Computer Organization and Architecture lecture materials. Performance analysis topics include execution time, CPI, instruction count, memory hierarchy, cache behavior, and power.

---

# One-Sentence Project Pitch

> **We will build fully offline Raspberry Pi smart glasses and experimentally determine whether an adaptive combination of specialized vision models and a small VLM can provide a better latency–energy–accuracy trade-off than running every visual task through a VLM.**
