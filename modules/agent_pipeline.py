"""
Mr.Creative Agent Pipeline
Orchestrates all agents to generate a full content batch.
"""

import json
import os
import time
import uuid
from datetime import datetime


def _check_job_control(job, db):
    """Check pause/stop flags. Returns True to continue, False to stop."""
    while True:
        db.session.refresh(job)
        if job.control_action == 'stop':
            job.status = 'complete'
            job.message = f'Stopped by user at {job.progress}%'
            job.completed_at = datetime.now()
            db.session.commit()
            return False
        if job.control_action == 'pause':
            job.message = 'Paused — waiting to resume...'
            db.session.commit()
            time.sleep(3)
            continue
        return True


def run_agent_pipeline(app, job_id):
    """Run the full agent pipeline for a job. Called in a background thread."""
    with app.app_context():
        from models import db, AgentJob, BrandKit, Collection, Generation
        from modules.agents import AgentEngine
        from modules.pollinations_api import PollinationsAPI

        job = AgentJob.query.get(job_id)
        if not job:
            print(f"[Pipeline] Job {job_id} not found!")
            return

        brand_kit = BrandKit.query.get(job.brand_kit_id)
        if not brand_kit:
            job.status = 'failed'
            job.error_message = 'Brand kit not found'
            db.session.commit()
            return

        groq_key = app.config.get('GROQ_API_KEY', '')
        if not groq_key:
            job.status = 'failed'
            job.error_message = 'Groq API key not configured'
            db.session.commit()
            return

        engine = AgentEngine(
            groq_api_key=groq_key,
            cerebras_api_key=app.config.get('CEREBRAS_API_KEY'),
        )
        pollinations = PollinationsAPI()

        try:
            # Initialize so later references are always bound regardless of branch taken
            brand_analysis = {}

            # ── Clamp target count ──
            job.target_count = max(1, min(25, job.target_count or 5))

            # ── Check if all content types support direct mode (skip LLM entirely) ──
            content_types = json.loads(job.content_types) if job.content_types else None
            direct_types = {'a_plus', 'model_photography'}
            all_direct = content_types and all(t in direct_types for t in content_types)

            if all_direct:
                # DIRECT MODE: skip Steps 1-3, use expert prompts
                from modules.prompt_library import CONTENT_TYPE_CONFIG
                import math

                # Use the first content type for prompt selection
                prompt_type = content_types[0] if content_types else 'a_plus'
                expert_prompts = CONTENT_TYPE_CONFIG.get(prompt_type, {}).get('expert_prompts', [])
                if not expert_prompts:
                    raise RuntimeError(f'No expert prompts for {prompt_type} in prompt_library')

                # Build prompts list (same format as Agent 3 output)
                prompts = []
                content_plan = []
                for i in range(job.target_count):
                    prompt_text = expert_prompts[i % len(expert_prompts)]
                    prompts.append({
                        'id': i + 1,
                        'prompt': prompt_text,
                        'negative_prompt': '',
                        'engine': 'flow',
                        'width': 1024,
                        'height': 1024,
                    })
                    content_plan.append({
                        'id': i + 1,
                        'type': prompt_type,
                        'title': f'{prompt_type} Image {i + 1}',
                    })

                job.status = 'generating'
                job.current_agent = 'Image Generator'
                job.progress = 40
                job.message = f'Direct mode ({prompt_type}): {job.target_count} images, no LLM needed'
                job.content_plan = json.dumps(content_plan)
                job.prompts = json.dumps(prompts)
                job.brand_analysis = json.dumps({})
                db.session.commit()
                print(f"[Pipeline] Direct mode ({prompt_type}): {job.target_count} images, skipping LLM")

            else:
                # NON-A+ FLOW: run Steps 1-3 with LLM
                # ── Step 1: Brand Analysis ──
                job.status = 'analyzing'
                job.current_agent = 'Brand Analyst'
                job.progress = 5
                job.message = 'Analyzing brand identity...'
                db.session.commit()

                brand_analysis = engine.analyze_brand(brand_kit)
                job.llm_provider = 'cerebras' if engine._using_cerebras else 'groq'
                db.session.commit()
                job.brand_analysis = json.dumps(brand_analysis)
                job.progress = 15
                db.session.commit()

                if not _check_job_control(job, db):
                    return

                # ── Step 2: Content Planning ──
                job.status = 'planning'
                job.current_agent = 'Content Strategist'
                job.progress = 20
                job.message = f'Planning {job.target_count} content pieces...'
                db.session.commit()

                content_types = json.loads(job.content_types) if job.content_types else None
                content_plan = engine.plan_content(
                    brand_analysis, brand_kit,
                    target_count=job.target_count,
                    content_types=content_types
                )
                content_plan = content_plan[:job.target_count]
                job.content_plan = json.dumps(content_plan)
                job.progress = 30
                db.session.commit()

                if not _check_job_control(job, db):
                    return

                # ── Step 3: Prompt Crafting ──
                job.status = 'crafting'
                job.current_agent = 'Prompt Crafter'
                job.progress = 35
                job.message = f'Crafting {len(content_plan)} prompts...'
                db.session.commit()

                if job.reference_image:
                    ref_abs = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'static', job.reference_image
                    )
                    engine._reference_image_path = ref_abs

                prompts = engine.craft_prompts(content_plan, brand_analysis, brand_kit)
                job.prompts = json.dumps(prompts)
                job.progress = 40
                db.session.commit()

                if not _check_job_control(job, db):
                    return

            # ── Step 4: Image Generation via Flow Bot ──
            job.status = 'generating'
            job.current_agent = 'Image Generator'
            job.message = 'Preparing Flow bot...'
            db.session.commit()

            # Create collection for this job
            collection = Collection(
                user_id=job.user_id,
                name=f"Agent — {brand_kit.name}",
                description=f"Generated by Mr.Creative Agent | {job.target_count} pieces | {brand_kit.tone} tone",
            )
            db.session.add(collection)
            db.session.commit()
            job.collection_id = collection.id
            db.session.commit()

            # Output directory
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'static', 'outputs', f'collection_{collection.id}'
            )
            os.makedirs(output_dir, exist_ok=True)

            results = []
            total = len(prompts)

            # Group prompts into batches of 4 (Flow generates up to 4 per run)
            batches = []
            for i in range(0, total, 4):
                batch = prompts[i:i+4]
                batches.append(batch)

            image_index = 0
            from modules.flow_runner import FlowSession

            session = FlowSession()
            if not session.start():
                raise RuntimeError('Could not start Flow session')

            try:
              for batch_num, batch in enumerate(batches):
                progress = 40 + int((batch_num / len(batches)) * 45)
                job.progress = progress
                job.message = f'Flow batch {batch_num+1}/{len(batches)} — generating {len(batch)} images...'
                db.session.commit()

                # Use first prompt in batch (Flow creates variations)
                prompt_item = batch[0]
                prompt_text = prompt_item.get('prompt', '') if isinstance(prompt_item, dict) else str(prompt_item)
                width = int(prompt_item.get('width', 1024)) if isinstance(prompt_item, dict) else 1024
                height = int(prompt_item.get('height', 1024)) if isinstance(prompt_item, dict) else 1024

                # Aspect ratio: user override or from content plan
                if hasattr(job, 'aspect_ratio') and job.aspect_ratio and job.aspect_ratio != 'mixed':
                    ar = job.aspect_ratio
                elif width > height:
                    ar = '16:9'
                elif height > width:
                    ar = '9:16'
                else:
                    ar = '1:1'

                print(f"[Pipeline] Batch {batch_num+1}: '{str(prompt_text)[:50]}...' | {ar} | x{len(batch)}")

                try:
                    # Reference image path (only for first batch — Flow keeps it after)
                    ref_image = None
                    if job.reference_image:
                        ref_image = os.path.join(
                            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'static', job.reference_image
                        )
                        if not os.path.exists(ref_image):
                            ref_image = None

                    files = session.run_batch(
                        prompt=prompt_text,
                        aspect_ratio=ar,
                        count=len(batch),
                        output_dir=output_dir,
                        reference_image=ref_image,
                        is_first=(batch_num == 0),
                    )

                    for j, filepath in enumerate(files):
                        plan_idx = image_index + j
                        plan_item = content_plan[plan_idx] if plan_idx < len(content_plan) else {}

                        rel_path = os.path.relpath(filepath,
                            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
                        ).replace('\\', '/')

                        gen = Generation(
                            user_id=job.user_id,
                            collection_id=collection.id,
                            output_path=rel_path,
                            pomelli_feature='agent',
                            status='completed',
                            tags=(str(plan_item.get('title', '')) + ' | ' + str(prompt_text)[:100]),
                        )
                        db.session.add(gen)
                        db.session.commit()

                        results.append({
                            'id': plan_idx + 1,
                            'filename': os.path.basename(filepath),
                            'path': rel_path,
                            'engine': 'flow',
                            'title': str(plan_item.get('title', f'Image {plan_idx+1}')),
                            'type': str(plan_item.get('type', 'unknown')),
                        })

                    print(f"[Pipeline] Batch {batch_num+1} done: {len(files)} images")

                except Exception as e:
                    print(f"[Pipeline] Batch {batch_num+1} failed: {e}")
                    import traceback
                    traceback.print_exc()
                    for j in range(len(batch)):
                        results.append({
                            'id': image_index + j + 1,
                            'error': str(e)[:100],
                            'engine': 'flow',
                        })

                image_index += len(batch)
                time.sleep(15)  # Pause between batches to avoid Flow rate-limiting

                if not _check_job_control(job, db):
                    session.close()
                    return
            finally:
                session.close()

            job.results = json.dumps(results)
            job.progress = 90
            db.session.commit()

            # ── Step 5: Post-Processing (logo, text, border, rembg) ──
            job.status = 'processing'
            job.current_agent = 'Post-Processor'
            job.progress = 92
            job.message = 'Applying brand elements (logo, text, border)...'
            db.session.commit()

            from modules.post_processor import PostProcessor
            processor = PostProcessor(brand_kit)
            results = processor.process_batch(results, content_plan, output_dir)

            # ── Step 5a: Color Correction (optional) ──
            post_opts = json.loads(job.post_options) if hasattr(job, 'post_options') and job.post_options else {}
            if post_opts.get('color_correct', False) or post_opts.get('brand_tint', False):
                job.message = 'Applying color correction...'
                db.session.commit()
                try:
                    from modules.color_correction import process_image as cc_process
                    for result in results:
                        if 'error' in result:
                            continue
                        img_path = os.path.join(output_dir, result.get('filename', ''))
                        if os.path.exists(img_path):
                            tint_color = brand_kit.primary_color if post_opts.get('brand_tint') else None
                            cc_process(img_path, hex_color=tint_color)
                    print(f"[Pipeline] Color correction applied")
                except Exception as e:
                    print(f"[Pipeline] Color correction skipped: {e}")

            if not _check_job_control(job, db):
                return

            # ── Step 5b: AI Copywriting (captions + hashtags) ──
            job.current_agent = 'Copywriter'
            job.progress = 94
            job.message = 'Generating captions and hashtags...'
            db.session.commit()

            try:
                from modules.copywriter import Copywriter
                writer = Copywriter(
                    groq_api_key=groq_key,
                    cerebras_api_key=app.config.get('CEREBRAS_API_KEY'),
                )
                results = writer.generate_batch_captions(
                    results, content_plan,
                    brand_name=brand_kit.name,
                    tone=brand_kit.tone or 'professional',
                )
            except Exception as e:
                print(f"[Pipeline] Copywriting skipped: {e}")

            # ── Step 6: Quality Review ──
            job.status = 'reviewing'
            job.current_agent = 'Quality Reviewer'
            job.progress = 95
            job.message = 'Reviewing quality...'
            db.session.commit()

            reviewed = engine.review_results(content_plan, results, brand_analysis)
            job.results = json.dumps(reviewed)

            # ── Complete ──
            successful = len([r for r in reviewed if 'error' not in r])
            job.status = 'complete'
            job.current_agent = ''
            job.progress = 100
            job.message = f'Done! {successful}/{total} images generated'
            job.completed_at = datetime.now()
            db.session.commit()

            print(f"[Pipeline] Job {job_id} complete! {successful}/{total} images generated")

        except Exception as e:
            print(f"[Pipeline] Job {job_id} failed: {e}")
            import traceback
            traceback.print_exc()
            try:
                db.session.rollback()
                job = AgentJob.query.get(job_id)
                if job:
                    job.status = 'failed'
                    job.error_message = str(e)[:500]
                    db.session.commit()
            except Exception:
                db.session.rollback()