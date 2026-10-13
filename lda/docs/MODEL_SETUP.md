# Model setup (one-time)

The agent's "brain" is an on-device vision model - **Gemma 4 E2B** (LiteRT-LM
format). It runs **fully offline** after a one-time ~3-4 GB download. Use **Wi-Fi**.

## Get the model and import it

1. In a browser (phone or PC), create a **free Hugging Face account** and sign in:
   https://huggingface.co/join
2. Open the Gemma 4 E2B LiteRT page and tap **"Agree and access repository"** to
   accept Google's Gemma license (instant):
   https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm
3. Open the **Files** tab and download the plain **`.litertlm`** file
   (e.g. `gemma-4-E2B-it-int4.litertlm`) to your **Downloads**.
   - Do NOT pick a `.mediatek...` file (that's for MediaTek chips; your Fold is
     Snapdragon) or a `-Web` file (browsers only). Only the plain `.litertlm`.
4. In Local Device Agent, tap **Import model file**, pick it from Downloads, and
   wait for the copy to finish -> "Model ready".

(Optional) To confirm your phone can run Gemma before downloading, install
**Google AI Edge Gallery** (Play Store, or https://github.com/google-ai-edge/gallery)
and try Gemma 4 E2B there.

## Notes
- After import, no internet is needed for the agent to think.
- The model and your screen never leave the device.
- The file stays in the app's private storage; you can delete the Downloads copy.
- The in-app "Download model (automatic)" button is usually blocked by the Gemma
  license gate - use the Import steps above instead.
- All Gemma 4 sizes accept images (vision); the agent sends a screenshot each step.
- Switching to a lighter or non-local model is a planned option (see README).

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

