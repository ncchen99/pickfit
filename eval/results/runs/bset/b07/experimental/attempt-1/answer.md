# Offline phone tutor: what to build

## Main recommendation

Don't rely on one "trained" model. Build three parts:

1. **A small instruction-tuned model** (about 1–4B parameters, compressed to 4-bit so it fits on a phone) that writes the explanations.
2. **RAG over your textbooks.** RAG (retrieval-augmented generation) means the app first finds the relevant textbook passages, then hands them to the model. This is what keeps answers tied to the books and the syllabus.
3. **A tagged question bank** stored as a plain database, not inside the model. Practice works by looking up questions in that database. The model's job there is to explain and give feedback.

Do the heavy work on your computer before you ship: cleaning the textbooks, tagging questions, writing worked solutions and generating extra practice questions. A large model can help with all of that. The phone then only does lookup plus short answers. That split is the most important design decision for a tiny offline model.

**Assumptions:** mostly mid-range Android phones with 4–8 GB of RAM, English-language content, and at least one subject with maths in it. Tell me if any of these is wrong.

## Which model

| Phone RAM | Start with (well-known baselines) | Newer candidates to test |
|---|---|---|
| 4 GB | Gemma 3 1B, Qwen3 1.7B | Qwen 3.5 0.8B / 2B |
| 6–8 GB | Gemma 3 4B, Phi-4-mini (3.8B) | Gemma 4 E2B (~1.5 GB), Qwen 3.5 4B |

Check the newer 2026 models (Gemma 4 edge versions, Qwen 3.5 small) on their Hugging Face model cards. The benchmark figures I found online come from blog-style sources and contradict each other. Choose by running your own test set: about 100 real student questions plus past-paper items, scored against the mark schemes, on your cheapest target phone. Also check the licences before you ship. Qwen uses Apache-2.0; Gemma has its own terms.

For searching the textbooks you also need a small **embedding model**, which turns text into numbers so similar passages can be found. Options include EmbeddingGemma (~300M) or bge-small / MiniLM (~30–130 MB). Combine it with keyword search (BM25). Textbook terms like "mitosis" or "Le Chatelier" match very reliably by keyword. On the phone, SQLite with the sqlite-vec extension can hold both the passages and the search index.

## RAG, fine-tuning, or both?

**Use RAG for the content. Fine-tune only for behaviour, and only if you need to.**

- **Don't** try to teach a 1–4B model the textbooks by training it. Small models memorise facts unreliably and then make things up confidently. With RAG you can show the page and section each answer came from, and you can update content without retraining.
- **You can** fine-tune later with LoRA, a cheap method for adjusting a model. Unsloth on a free or cheap Colab GPU handles 1–4B models. Use it to teach *style and scope*: answer at this grade level, use the passages it was given, show working, say "that's outside your syllabus", ask a guiding question instead of handing over the answer.
- **How to make training data:**
  - Take past-paper questions and textbook-style questions.
  - Retrieve the matching passages.
  - Have a large model write the ideal tutor answer.
  - Have a teacher spot-check the answers.
  - 1,000–3,000 good examples is plenty.

  This approach is called distillation.
- **Order:** get plain RAG plus good prompts working first. Fine-tune only if your test set shows a specific problem with tone or staying in scope.

## Practice questions

1. **Find past and practice questions:** before shipping, use a big model to tag every question with subject, syllabus topic, difficulty, marks, year and its mark scheme. Have a person check the tags. On the phone, picking a topic is then a normal database query, which is instant and reliable.
2. **Mark answers:** the student answers, and the small model compares the answer with the stored mark scheme and gives feedback. Small models handle this well because the correct answer is right there in front of them.
3. **"Similar" questions:**
   - **Best option:** generate thousands of variants on your computer with a large model, have them reviewed, and ship them as part of the bank.
   - **Maths and physics:** use templates with changing numbers, and have code compute the correct answer. Never let the small model do the arithmetic.
   - **Essay and theory subjects:** letting the model rephrase questions live on the phone is acceptable, but label those questions as "generated".

## Install and first-run steps (prototype on your Mac first)

I haven't run any of these. pickfit, the software recommendation tool I checked, had no tested tool matching this use case, so these are standard, well-known tools.

1. **Try models on your computer.** Install Ollama from ollama.com (or `brew install ollama`), then:
   ```
   ollama pull gemma3:1b
   ollama pull qwen3:1.7b
   ollama run gemma3:1b "Explain osmosis for a 15-year-old in 4 sentences."
   ```
   For newer models, look up the exact names in the ollama.com library (Gemma 4 / Qwen 3.5 small); I'm not certain of them.
2. **Prepare the textbooks.** Convert the PDFs to Markdown with equations kept as LaTeX, using Docling or Marker. Split the text into chunks of about 300–500 tokens, each labelled with subject, chapter, syllabus code and page.
3. **Build a small RAG prototype** in Python: embed the chunks, store them in SQLite with sqlite-vec, find the top 3 chunks plus keyword matches for each question, and send them to the model through Ollama's local API. Use a system prompt along the lines of: *"Answer only from the passages. Cite the page. If the passages don't cover it, say it's outside the syllabus."*
4. **Test on a real phone.** Install Google's **AI Edge Gallery** app (Android, and iOS where available), load a candidate model, and measure speed and memory use on your cheapest target device.
5. **Build the app.** Choose one route:
   - **Google LiteRT-LM** (formerly the MediaPipe LLM Inference API): native Android/iOS, Gemma models best supported.
   - **llama.cpp**: works with any GGUF model file. Use it through `llama.rn` in React Native, or native bindings.
   - **MLC LLM**: another cross-platform option.

   As a beginner, React Native or Flutter with a llama.cpp binding plus SQLite is the gentlest path.

## Challenges and workarounds

| Challenge | Workaround |
|---|---|
| Made-up answers | Strict "use the passages" prompt, citations, a confidence check ("no matching passage → say so"), test set |
| Weak at maths and arithmetic | Show stored worked solutions; do calculations in code; let the model explain the steps, not compute them |
| Slow on phones (reading long input is costly) | 2–3 short chunks, short answers, stream the text as it's generated, cache the system prompt |
| Wide range of phone RAM | Two model sizes (1B "lite" vs 4B "full"), chosen at install time |
| Download size (model 0.5–2.5 GB + index) | Separate download per subject; sideload over USB or SD card for schools with no internet |
| Equations and diagrams in PDFs | Clean up LaTeX by hand for key chapters; show figures as images rather than asking the model to read them |
| Students drifting off-topic or misusing it | Syllabus-scope prompt, topic filter, guiding-question tutoring style, age-appropriate refusals |
| Heat and battery | Limit answer length; run the model only when needed |
| Copyright | Confirm you have the right to redistribute the textbooks and past papers inside an app |
| Updates while offline | Version your content packs so new ones can be sideloaded |

**Suggested order:** first a Mac prototype with one subject and plain RAG, then a test set, then a phone test, then the question bank, then the other subjects, and fine-tuning last and only if needed.

Sources:
- [Ertas: best models for on-device mobile AI 2026](https://www.ertas.ai/blog/best-models-on-device-mobile-ai-2026)
- [Qwen 3.5 Small for phones](https://toolhalla.ai/blog/qwen-3-5-small-best-llm-for-phone-2026)
- [On-Device AI Leaderboard 2026](https://covebase.pages.dev/en/on-device-ai/leaderboard)
- [Edge/Mobile LLM Leaderboard](https://awesomeagents.ai/leaderboards/edge-mobile-llm-leaderboard/)
- [On-Device LLMs in 2026 (Edge AI & Vision)](https://www.edge-ai-vision.com/?p=56644)