# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time
import threading
import json
from typing import Dict, Any
from google.genai import types
import json_repair
from utils import generation_utils
from utils.base64_rw_helper import read_base64
from ..base_agent import BaseAgent

def format_chat_history(chat_history, data):
    i, j = data['current_critic_round']
    ctx = data.get(f'target_diagram_contextualize_each_turn_{i}-0') or {}
    n_user = sum((1 for t in chat_history if t['role'] == 'user'))
    ret, i_turn = ([], 0)
    for turn in chat_history:
        content = turn['content']
        if turn['role'] == 'user':
            i_turn += 1
            label = 'User (latest turn)' if i_turn == n_user else f'User (turn {i_turn})'
            ret.append(f'{label}: {content}')
            if j > 0 or i_turn < n_user:
                ret[-1] += ' [Context: {}]'.format(ctx.get(f'context_user_turn{i_turn}', 'n/a'))
        else:
            assert turn['role'] == 'assistant'
            ret.append(f'Assistant: [Diagram{i_turn + 1}] generated.')
            if j > 0 or i_turn + 1 < n_user:
                ret[-1] += ' [Context: {}]'.format(ctx.get(f'context_diagram{i_turn + 1}', 'n/a'))
    return '\n'.join(ret)

def format_chat_history_with_images(chat_history, data):
    prior_fields = data.get('prior_preferred_candidates', [])
    assert len(chat_history) == (len(prior_fields) + 1) * 2
    ret, i_turn, version_idx = ([], 0, 0)
    for turn in chat_history:
        content = turn['content']
        if turn['role'] == 'user':
            i_turn += 1
            label = f'User (turn {i_turn})'
            ret.append({'type': 'text', 'text': f'{label}: {content}'})
        else:
            assert turn['role'] == 'assistant'
            ret.append({'type': 'text', 'text': f'Assistant: [Diagram{i_turn + 1}] generated. (attached below)'})
            if version_idx < len(prior_fields):
                field = prior_fields[version_idx]
                version_idx += 1
            else:
                field = data.get('eval_image_field')
            image_base64 = read_base64(data.get(field))
            if image_base64 and len(image_base64) > 100:
                ret.append({'type': 'image', 'source': {'type': 'base64', 'data': image_base64, 'media_type': 'image/jpeg'}})
            else:
                ret.append({'type': 'text', 'text': '[SYSTEM NOTE] No valid image was generated in this turn. The user was presented with the prior image.'})
    return ret

class PBInteract(BaseAgent):
    """Feedback Agent to integrate human feedback"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.model_name = self.exp_config.main_model_name
        self.task_config = {'task_name': 'diagram', 'context_labels': ['Methodology Section', 'Figure Caption', 'Chat History']}

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cfg = self.task_config
        task_name = cfg['task_name']
        eval_image_field = data.get('eval_image_field')
        assert eval_image_field and eval_image_field.endswith('_base64_jpg')
        base64_key = eval_image_field
        desc_key = eval_image_field.replace('_base64_jpg', '')
        out_round = data['current_critic_round']
        detailed_description = data.get(desc_key, '')
        image_base64 = read_base64(data.get(base64_key))
        content = data['content']
        if isinstance(content, (dict, list)):
            content = json.dumps(content)
        visual_intent = data['visual_intent']
        i, j = out_round
        diagram_label = f'[Diagram{i}]' if j == 0 else f'[Diagram{i}.{j}]'
        diagram_label_base = f'[Diagram{i}]'
        r = f'{i}-{j}'
        if j == 0:
            context_input = format_chat_history_with_images(data['chat_history'], data)
            context_input.append({'type': 'text', 'text': f"## User's Initial Request\n\n{cfg['context_labels'][0]}: {content}\n\n{cfg['context_labels'][1]}: {visual_intent}"})
            n_user = sum((1 for t in data['chat_history'] if t['role'] == 'user'))
            context_schema = {}
            for n in range(1, n_user + 1):
                context_schema[f'context_diagram{n}'] = f'Context note for [Diagram{n}].'
                context_schema[f'context_user_turn{n}'] = f'Context note for user turn {n}.'
            context_schema_to_build = json.dumps(context_schema, indent=2)
            response_list = generation_utils.call_model_with_retry_async(model_name=self.model_name, contents=context_input, config=types.GenerateContentConfig(system_instruction=CONTEXT_SYSTEM_PROMPT.replace('{SCHEMA_TO_BUILD}', context_schema_to_build), temperature=self.exp_config.temperature, candidate_count=1, max_output_tokens=50000), max_attempts=5, retry_delay=5)
            cleaned_response = response_list[0].replace('```json', '').replace('```', '').strip()
            try:
                context_result = json_repair.loads(cleaned_response)
                if not isinstance(context_result, dict):
                    context_result = {}
            except Exception as e:
                context_result = {}
                print(e, cleaned_response)
            data[f'target_{task_name}_contextualize_each_turn_{r}'] = context_result
        critique_target = f'Critique Target: {diagram_label} (attached below)'
        if j > 0:
            critique_target += f', revised from [Diagram{i}]'
        content_list = [{'type': 'text', 'text': critique_target}]
        if image_base64 and len(image_base64) > 100:
            content_list.append({'type': 'image', 'source': {'type': 'base64', 'data': image_base64, 'media_type': 'image/jpeg'}})
        else:
            print(f'⚠️ [Critic] No valid image found for round {out_round}. Using text-only critique mode.')
            content_list.append({'type': 'text', 'text': '\n[SYSTEM NOTICE] The diagram could not be generated based on the current description. Please check the description and provide a revised version.'})
        chat_history = format_chat_history(data['chat_history'], data)
        content_list.append({'type': 'text', 'text': f"{cfg['context_labels'][0]}: {content}\n\n{cfg['context_labels'][1]}: {visual_intent}\n\n{cfg['context_labels'][2]}:\n\n{chat_history}"})
        is_general_critic = j > 0
        if is_general_critic:
            system_prompt = SYSTEM_PROMPT_CRITIQUE_ONLY.replace('{DIAGRAM_LABEL}', diagram_label).replace('{DIAGRAM_LABEL_BASE}', diagram_label_base)
        else:
            system_prompt = SYSTEM_PROMPT_LATEST_TURN.replace('{DIAGRAM_LABEL}', diagram_label)
        n_prior_turns = sum((1 for t in data['chat_history'] if t['role'] == 'user')) - 1
        schema = {'critique_latest_turn': 'Your critique against the latest user turn.'}
        for n in range(1, n_prior_turns + 1):
            schema[f'critique_prior_turn{n}'] = f'Your critique against user turn {n}.'
        schema['critique_source_content'] = 'Your critique against the Methodology Section and Figure Caption.'
        schema['critique_presentation'] = 'Your critique of the overall visual clarity, presentation, and legend.'
        schema_to_build = json.dumps(schema, indent=2)
        content_list.append({'type': 'text', 'text': (STEP1_CRITIQUE_PROMPT_CRITIQUE_ONLY if is_general_critic else STEP1_CRITIQUE_PROMPT_LATEST_TURN).replace('{SCHEMA_TO_BUILD}', schema_to_build).replace('{DIAGRAM_LABEL}', diagram_label)})
        conversation = [content_list]
        response_list = generation_utils.call_model_with_retry_async(model_name=self.model_name, contents=conversation, config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=self.exp_config.temperature, candidate_count=1, max_output_tokens=50000), max_attempts=5, retry_delay=5, multiturn_input=True)
        if response_list[0] is not None:
            conversation.append(types.Content(role='model', parts=[types.Part.from_text(text=response_list[0])]))
        cleaned_response = response_list[0].replace('```json', '').replace('```', '').strip()
        try:
            eval_result = json_repair.loads(cleaned_response)
            if not isinstance(eval_result, dict):
                eval_result = {}
        except Exception as e:
            eval_result = {}
            print(e, cleaned_response)
        for k, v in eval_result.items():
            if k.startswith('critique_'):
                sep = '_' if k.startswith('critique_prior_turn') else ''
                data[f'target_{task_name}_{k}{sep}{r}'] = str(v)
        conversation.append([{'type': 'text', 'text': STEP2_GATING_PROMPT.replace('{DIAGRAM_LABEL}', diagram_label)}])
        response_list = generation_utils.call_model_with_retry_async(model_name=self.model_name, contents=conversation, config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=self.exp_config.temperature, candidate_count=1, max_output_tokens=50000), max_attempts=5, retry_delay=5, multiturn_input=True)
        if response_list[0] is not None:
            conversation.append(types.Content(role='model', parts=[types.Part.from_text(text=response_list[0])]))
        if response_list[0].strip().lower().startswith('no'):
            data[f'target_{task_name}_critic_suggestions{r}'] = 'No changes needed.'
            return data
        conversation.append([{'type': 'text', 'text': f"{STEP3_REWRITE_PROMPT.replace('{DIAGRAM_LABEL}', diagram_label)}\n\n## Detailed Description:\n\n{detailed_description}\n"}])
        response_list = generation_utils.call_model_with_retry_async(model_name=self.model_name, contents=conversation, config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=self.exp_config.temperature, candidate_count=1, max_output_tokens=50000), max_attempts=5, retry_delay=5, multiturn_input=True)
        cleaned_response = response_list[0].replace('```json', '').replace('```', '').strip()
        try:
            eval_result = json_repair.loads(cleaned_response)
            if not isinstance(eval_result, dict):
                eval_result = {}
        except Exception as e:
            eval_result = {}
            print(e, cleaned_response)
        critic_suggestions = eval_result.get('critic_suggestions', 'No changes needed.')
        revised_description = eval_result.get('revised_description', 'No changes needed.')
        if str(revised_description).strip() == 'No changes needed.':
            data[f'target_{task_name}_critic_suggestions{r}'] = 'No changes needed.'
            return data
        data[f'target_{task_name}_critic_suggestions{r}'] = str(critic_suggestions)
        data[f'target_{task_name}_critic_desc{r}'] = str(revised_description)
        return data
CONTEXT_SYSTEM_PROMPT = "## ROLE\nYou are a Lead Visual Designer for top-tier AI conferences (e.g., NeurIPS 2025), acting as the note-taker for a diagram revision conversation.\n\n## TASK\n\nYou are given the full chat history between a user and an AI diagram-generation system. Each [DiagramN] is attached as an image. The user's initial request (the 'Methodology Section' and 'Figure Caption') precedes [Diagram1], and each user turn reacts to the diagram generated right before it.\n\nYour task is to annotate the chat history so that it remains fully interpretable without the images: write exactly one context note for every turn.\n-   **For each assistant turn [DiagramN]:** summarize what the diagram shows; enumerate the concrete changes made relative to [DiagramN-1], if a previous version exists, and whether those changes addresses the request in user turn N-1; and, judging from the user's subsequent reply, state which aspects the user appears to accept and which remain unsatisfactory.\n-   **For each user turn:** identify the exact element(s) in the diagram that the utterance refers to, including their location and current visual state; state precisely what is wrong with them; and specify what change would resolve the complaint.\n\nEach note must be self-contained: an utterance together with its note must be sufficient for a reader who has never seen the images to reconstruct what was shown, what the user objected to, and why.\n\n## OUTPUT\n\nProvide your response strictly in the following JSON format, one key per turn in conversation order.\n\n```json\n{SCHEMA_TO_BUILD}\n```"
SYSTEM_PROMPT_LATEST_TURN = '## ROLE\nYou are a Lead Visual Designer for top-tier AI conferences (e.g., NeurIPS 2025).\n\n## TASK\n\nYour task is to provide a thorough critique and refinement of the target diagram, {DIAGRAM_LABEL}, based on the **user\'s request**. You are provided with the initial request (\'Methodology Section\' and \'Figure Caption\') and the iterative user feedback provided via \'Chat History\'. Please preserve the correct elements from previous turns, and directly address the feedback given in the **latest** turn of the Chat History.\n\nThis is a multi-turn process carried out in three steps. At each step, follow the specific instruction given in that turn — do not run ahead or fold later steps into an earlier one.\n    1.  **Critique.** Walk the target diagram against every constraint one by one and write up the per-aspect critique, noting for each issue what is wrong and how it should be fixed.\n    2.  **Decide.** Judge whether the diagram still needs revision, and answer with a single word as instructed.\n    3.  **Refine.** Only if revision is needed, you will then be shown the Detailed Description that renders the target diagram, and asked to synthesize your critique into concrete suggestions and a fully revised description.\n\n## REVISION RULES - WHAT YOU MUST ENSURE\n\n1. Chat history\n    -   Address the user\'s requirements in both the latest turn and all prior turns. The target diagram builds upon all previous turns, so you should treat past requests differently from the most recent one.\n    -   **Prior turns:**\n        -   **Assessing satisfaction:** If a user stops mentioning a specific issue, it usually means the functionality was successfully implemented. Don\'t assume it\'s still broken.\n        -   **Preserving elements:** Inspect the diagram to find components that correspond to earlier requests. This reveals what the user likes. Be sure to preserve these successful elements faithfully, without degrading or undoing them.\n    -   **The latest turn:** The request in the **latest** turn directly targets {DIAGRAM_LABEL} and, by definition, hasn\'t been addressed yet. Identify exactly what is wrong or missing, determine how to fix it, and ensure your revised description fully resolves the issue.\n\n2. Source Content\n    -   **Fidelity & Alignment:** Ensure the diagram accurately reflects the method described in the "Methodology Section" and aligns with the "Figure Caption." Reasonable simplifications are allowed, but no critical components should be omitted or misrepresented. Also, the diagram should not contain any hallucinated content. Consistency with the provided methodology section & figure caption is always the most important thing.\n    -   **Text QA:** Check for typographical errors, nonsensical text, or unclear labels within the diagram. Suggest specific corrections.\n    -   **Validation of Examples:** Verify the accuracy of illustrative examples. If the diagram includes specific examples to aid understanding (e.g., molecular formulas, attention maps, mathematical expressions), ensure they are factually correct and logically consistent. If an example is incorrect, provide the correct version.\n    -   **Caption Exclusion:** Ensure the figure caption text (e.g., "Figure 1: Overview...") is **not** included within the image visual itself. The caption should remain separate.\n\n3. Presentation\n    -   **Clarity & Readability:** Evaluate the overall visual clarity. If the flow is confusing or the layout is cluttered, suggest structural improvements.\n    -   **Legend Management:** Be aware that the description and diagram may include a text-based legend explaining color coding. Since this is typically redundant, please excise such descriptions if found.\n\n## HOW TO CRITIQUE - WALK EVERY CONSTRAINT ONE BY ONE\n\nDo NOT lump everything into a single blob. Go through the constraints sequentially and emit a SEPARATE critique entry for each, in this exact order:\n1. "critique_latest_turn": critique {DIAGRAM_LABEL} against the most recent user turn (shown as "User (latest turn)" in the Chat History). Identify exactly WHAT is wrong or missing for this request, its location and current visual state, and how the revised description will fix it.\n2. "critique_prior_turnN": emit one entry for EACH prior user turn, where N is the user turn\'s index shown as "User (turn N)" in the Chat History. In each, verify the target diagram still satisfies that turn\'s requirement, preserve the successful elements, and flag anything undone or degraded. If there are no prior turns, emit no such key.\n3. "critique_source_content": critique the target diagram against the \'Methodology Section\' and \'Figure Caption\' — fidelity & alignment, text QA, validation of examples, and caption exclusion.\n4. "critique_presentation": critique the target diagram for its overall visual clarity, presentation, and legend.\n\nEach critique entry should be long and specific, grounded in visual details, rather than a one-line verdict.\n\n## INPUT DATA\n-   **Target Diagram**: {DIAGRAM_LABEL} [the generated figure, attached as an image]\n-   **Detailed Description**: [The detailed description of the figure — withheld for now; it will be provided only at the refinement step (step 3)]\n-   **Methodology Section**: [Contextual content from the methodology section]\n-   **Figure Caption**: [Target figure caption]\n-   **Chat History**: [List of chat utterances from all turns. Each user turn is labeled "User (turn N)" or "User (latest turn)". Each prior turn includes a brief [Context: ...] note summarizing what that diagram showed or what that user turn requested. Focus on addressing the **LATEST** turn]'
SYSTEM_PROMPT_CRITIQUE_ONLY = '## ROLE\nYou are a Lead Visual Designer for top-tier AI conferences (e.g., NeurIPS 2025).\n\n## TASK\n\nYour task is to provide a thorough critique and refinement of the target diagram, {DIAGRAM_LABEL}, based on the user\'s full request, the source content, and the overall presentation. You are provided with the initial request (\'Methodology Section\' and \'Figure Caption\') and the iterative user feedback provided via \'Chat History\'.\n\nThis is a multi-turn process carried out in three steps. At each step, follow the specific instruction given in that turn — do not run ahead or fold later steps into an earlier one.\n    1.  **Critique.** Walk the target diagram against every constraint one by one and write up the per-aspect critique, noting for each issue what is wrong and how it should be fixed.\n    2.  **Decide.** Judge whether the diagram still needs revision, and answer with a single word as instructed.\n    3.  **Refine.** Only if revision is needed, you will then be shown the Detailed Description that renders the target diagram, and asked to synthesize your critique into concrete suggestions and a fully revised description.\n\n## REVISION RULES - WHAT YOU MUST ENSURE\n\n1. Chat history & requirements\n    -   **Prior turns:**\n        -   **Assessing satisfaction:** If a user stops mentioning a specific issue, it usually means the functionality was successfully implemented. Don\'t assume it\'s still broken.\n        -   **Preserving elements:** Inspect the diagram to find components that correspond to earlier requests. This reveals what the user likes. Be sure to preserve these successful elements faithfully, without degrading or undoing them.\n    -   **The latest turn:**\n        -   **Assessing satisfaction:** Step back and comprehensively verify if the target diagram satisfies the latest user request. The user\'s latest request originally targets {DIAGRAM_LABEL_BASE}, and {DIAGRAM_LABEL} has ALREADY been revised in response to the user\'s most recent turn. It MAY already have been addressed by that revision. However, the user has NOT yet seen this revision, so you CANNOT apply the "user stopped mentioning it, so it must be fixed" heuristic — it may still be unmet.\n        -   **Preserving elements:** If the diagram has already successfully addressed the latest user request, be sure to preserve these successful elements faithfully, without degrading or undoing them.\n    -   **Where this critique sits**: Since the diagram has already been revised to address the latest user request, your job now is to step back and comprehensively verify that the target diagram simultaneously satisfies EVERY constraint across all turns and the main context, and to catch any remaining general issues. Do NOT single out the latest turn or prioritize it.\n\n2. Source Content\n    -   **Fidelity & Alignment:** Ensure the diagram accurately reflects the method described in the "Methodology Section" and aligns with the "Figure Caption." Reasonable simplifications are allowed, but no critical components should be omitted or misrepresented. Also, the diagram should not contain any hallucinated content. Consistency with the provided methodology section & figure caption is always the most important thing.\n    -   **Text QA:** Check for typographical errors, nonsensical text, or unclear labels within the diagram. Suggest specific corrections.\n    -   **Validation of Examples:** Verify the accuracy of illustrative examples. If the diagram includes specific examples to aid understanding (e.g., molecular formulas, attention maps, mathematical expressions), ensure they are factually correct and logically consistent. If an example is incorrect, provide the correct version.\n    -   **Caption Exclusion:** Ensure the figure caption text (e.g., "Figure 1: Overview...") is **not** included within the image visual itself. The caption should remain separate.\n\n3. Presentation\n    -   **Clarity & Readability:** Evaluate the overall visual clarity. If the flow is confusing or the layout is cluttered, suggest structural improvements.\n    -   **Legend Management:** Be aware that the description and diagram may include a text-based legend explaining color coding. Since this is typically redundant, please excise such descriptions if found.\n\n## HOW TO CRITIQUE - WALK EVERY CONSTRAINT ONE BY ONE\n\nDo NOT lump everything into a single blob. Go through the constraints sequentially and emit a SEPARATE critique entry for each, in this exact order:\n1. "critique_latest_turn": critique {DIAGRAM_LABEL} against the most recent user turn (shown as "User (latest turn)" in the Chat History). Fold it in as one requirement among many — do not prioritize it — but do verify it is actually met, since the user has not reviewed this revision yet.\n2. "critique_prior_turnN": emit one entry for EACH prior user turn, where N is the user turn\'s index shown as "User (turn N)" in the Chat History. In each, verify the target diagram still satisfies that turn\'s requirement, preserve the successful elements, and flag anything undone or degraded. If there are no prior turns, emit no such key.\n3. "critique_source_content": critique the target diagram against the \'Methodology Section\' and \'Figure Caption\' — fidelity & alignment, text QA, validation of examples, and caption exclusion.\n4. "critique_presentation": critique the target diagram for its overall visual clarity, presentation, and legend.\n\nEach critique entry should be long and specific rather than a one-line verdict.\n\n## INPUT DATA\n-   **Target Diagram**: {DIAGRAM_LABEL} [the generated figure, attached as an image — revised from {DIAGRAM_LABEL_BASE} but not yet reviewed by the user]\n-   **Detailed Description**: [The detailed description of the figure — withheld for now; it will be provided only at the refinement step (step 3)]\n-   **Methodology Section**: [Contextual content from the methodology section]\n-   **Figure Caption**: [Target figure caption]\n-   **Chat History**: [List of chat utterances from all turns. Each user turn is labeled "User (turn N)" or "User (latest turn)". Each turn includes a brief [Context: ...] note summarizing what that diagram showed or what that user turn requested. Check the diagram against ALL turns, not just the latest]'
STEP1_CRITIQUE_PROMPT_CRITIQUE_ONLY = 'Please perform the first step: Critique. Walk {DIAGRAM_LABEL} against every constraint one by one and emit the per-aspect critique, noting for each issue what is wrong and how it should be fixed.\n\n## OUTPUT\nProvide your response strictly in the following JSON format.\n\n```json\n{SCHEMA_TO_BUILD}\n```'
STEP1_CRITIQUE_PROMPT_LATEST_TURN = 'Please perform the first step: Critique. Walk {DIAGRAM_LABEL} against every constraint one by one and emit the per-aspect critique, prioritizing the LATEST user turn, and noting for each issue what is wrong and how it should be fixed.\n\n## OUTPUT\nProvide your response strictly in the following JSON format.\n\n```json\n{SCHEMA_TO_BUILD}\n```'
STEP2_GATING_PROMPT = 'Please perform the second step: Decide. Based on your critique above, decide whether {DIAGRAM_LABEL} still needs any revision.\nAnswer with **a single word and nothing else**: "YES" if any revision is needed, "NO" if the diagram already satisfies every requirement and no changes are needed.'
STEP3_REWRITE_PROMPT = 'Please perform the third step: Refine. The Detailed Description that produced {DIAGRAM_LABEL} is now provided below; revise it based on your critique above, producing these two fields sequentially:\n1. "critic_suggestions": synthesize all of the above into concrete, actionable suggestions, trying to incorporate and balance all of the requirements above rather than fixing one at the expense of another.\n2. "revised_description": the fully revised detailed description incorporating every suggestion. Follow the "POSITIVE, SPECIFIC DESCRIPTIONS" rule below — state what the diagram SHOULD contain, affirmatively and specifically, not what it should avoid.\n\n** IMPORTANT: **\nYour Description should primarily be modifications based on the original description, rather than rewriting from scratch. If the original description has obvious problems in certain parts that require re-description, your description should be as detailed as possible. Semantically, clearly describe each element and their connections. Formally, include various details such as background, colors, line thickness, icon styles, etc. Remember: vague or unclear specifications will only make the generated figure worse, not better.\n\n** POSITIVE, SPECIFIC DESCRIPTIONS: **\nThe critique entries are where you diagnose what is WRONG — that is their job. But the "revised_description" itself must NOT carry that negative framing. It is fed to an image generator that renders what you affirmatively describe and tends to ignore — or even latch onto — negations.\n-   Do NOT phrase the description as "do not ...", "avoid ...", "no ...", "without ...", or "remove ..." — an image model cannot render an absence, and naming an unwanted element often causes it to appear.\n-   Instead, describe positively what SHOULD be there: the exact element, its content, position, size, color, and style that replaces the problem.\n-   Prevent errors by being MORE specific, not by prohibiting. Where something previously went wrong, add more concrete detail (exact text, counts, geometry, spatial relations) so the generator has no room to reintroduce the mistake.\n\n## OUTPUT\nProvide your response strictly in the following JSON format.\n\n```json\n{\n    "critic_suggestions": "Synthesize the above into concrete, actionable suggestions for improvement, trying to incorporate and balance all of the requirements above rather than fixing one at the expense of another. If the diagram is perfect, write \'No changes needed.\'",\n    "revised_description": "Insert the fully revised detailed description here, incorporating all your suggestions. Phrase it positively and specifically — describe what the diagram SHOULD contain (exact content, position, size, color, style), never what to avoid or remove. If no changes are needed, write \'No changes needed.\'"\n}\n```'
