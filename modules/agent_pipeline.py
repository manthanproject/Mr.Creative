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
            direct_types = {'model_photography'}
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
                prompts = []
                content_plan = []

                # Check if A+ content — skip Agent 1 & 2
                _ct = json.loads(job.content_types) if job.content_types else []
                _is_aplus = _ct and all(t == 'a_plus' for t in _ct)

                if _is_aplus:
                    job.status = 'crafting'
                    job.current_agent = 'A+ Prompt Generator'
                    job.progress = 30
                    job.message = f'Generating {job.target_count} A+ prompts with product image...'
                    db.session.commit()
                    from modules.aplus_prompt_generator import generate_listing_prompts
                    _info = {
                        'product_name': getattr(brand_kit, 'name', 'Product') if brand_kit else 'Product',
                        'features': [f.strip() for f in (getattr(brand_kit, 'description', '') or '').split(',') if f.strip()],
                        'brand_name': getattr(brand_kit, 'name', '') if brand_kit else '',
                    }
                    _ref_url = None
                    print(f"[Pipeline DEBUG] job.reference_image = {repr(job.reference_image)}")
                    if job.reference_image:
                        _ref_url = f'http://127.0.0.1:5000/static/{job.reference_image}'
                    print(f"[Pipeline DEBUG] _ref_url = {repr(_ref_url)}")
                    _ap = generate_listing_prompts(_info, count=job.target_count, image_url=_ref_url)
                    prompts = [{'prompt': p['prompt'], 'width': 1024, 'height': 1024, 'aspect_ratio': '1:1'} for p in _ap]
                    content_plan = [{'type': 'a_plus', 'id': i+1} for i in range(len(prompts))]
                    job.prompts = json.dumps(prompts)
                    job.content_plan = json.dumps(content_plan)
                    job.brand_analysis = json.dumps({})
                    job.progress = 40
                    print(f"[Pipeline] A+ shortcut: {len(prompts)} prompts ready (skipped Agent 1 & 2)")
                    db.session.commit()

                if not _is_aplus:
                    # ── Step 1: Brand Analysis ──
                    job.status = 'analyzing'
                    job.current_agent = 'Brand Analyst'
                    job.progress = 5
                    job.message = 'Analyzing brand identity...'
                    db.session.commit()

                    brand_analysis = engine.analyze_brand(brand_kit)
                    try:
                        from modules.night_orchestrator.llm import last_provider
                        job.llm_provider = last_provider
                    except ImportError:
                        job.llm_provider = 'groq'
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

                    # A+ content: use dedicated hyper-detailed prompt generator (1 prompt at a time)
                    _ctypes = json.loads(job.content_types) if job.content_types else []
                    _all_aplus = _ctypes and all(t == 'a_plus' for t in _ctypes)

                    if _all_aplus:
                        print(f"[Pipeline] A+ mode: {len(content_plan)} hyper-detailed prompts via aplus_prompt_generator")
                        job.message = f'Generating {len(content_plan)} detailed A+ prompts...'
                        db.session.commit()
                        from modules.aplus_prompt_generator import generate_listing_prompts
                        _info = {
                            'product_name': brand_kit.name or 'Product',
                            'category': getattr(brand_kit, 'category', '') or 'General',
                            'features': [f.strip() for f in (getattr(brand_kit, 'description', '') or '').split(',') if f.strip()],
                            'brand_name': brand_kit.name or '',
                            'style_notes': getattr(brand_kit, 'tone', '') or 'premium commercial',
                        }
                        _ref_url = None
                        if job.reference_image:
                            _ref_url = f'http://127.0.0.1:5000/static/{job.reference_image}'
                        _ap = generate_listing_prompts(_info, count=len(content_plan), image_url=_ref_url)
                        prompts = [{'prompt': p['prompt'], 'width': 1024, 'height': 1024, 'aspect_ratio': '1:1'} for p in _ap]
                        print(f"[Pipeline] A+ prompts ready: {len(prompts)}")
                    else:
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

            # Extension-based Flow (no Selenium)
            import uuid as _uuid
            from routes.extension import _state, _lock  # type: ignore[attr-defined]

            _prompt_texts: list[str] = []
            for p in prompts:
                if isinstance(p, dict):
                    _prompt_texts.append(str(p.get('prompt', '')))
                else:
                    _prompt_texts.append(str(p))

            _ref_url = None
            if job.reference_image:
                _ref_url = f'http://127.0.0.1:5000/static/{job.reference_image}'

            _ar = 'square'
            if hasattr(job, 'aspect_ratio') and job.aspect_ratio:
                _ar_map = {'1:1': 'square', '16:9': 'landscape', '9:16': 'story', '3:4': 'feed', '4:3': 'wide'}
                _ar = _ar_map.get(job.aspect_ratio, 'square')

            _dl_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
            _before = set(os.listdir(_dl_dir)) if os.path.exists(_dl_dir) else set()

            _fid = f'flow_{_uuid.uuid4().hex[:8]}'
            _fjob = {
                'job_id': _fid, 'job_type': 'flow',
                'prompts': _prompt_texts, 'image_url': _ref_url,
                'image_filename': os.path.basename(job.reference_image) if job.reference_image else 'product.jpg',
                'aspect_ratio': _ar, 'count': 1,
                'collection_id': collection.id,
                'start_time': time.time(),
                'content_types': json.loads(job.content_types) if job.content_types else [],
                'logo_path': getattr(brand_kit, 'logo_path', None) or '',
            }

            with _lock:
                _state['job_data'][_fid] = _fjob
                _routed = False
                _profiles = dict(_state.get('profiles') or {})
                for pid, info in _profiles.items():
                    caps = info.get('capabilities', [])
                    if 'flow_active' in caps:
                        _state['pending_commands'][pid] = _fjob
                        _routed = True
                        print(f'[Pipeline] Flow job {_fid} routed to {pid}')
                        break
                if not _routed:
                    _jq = _state.get('job_queue')
                    if not isinstance(_jq, list):
                        _jq = []
                        _state['job_queue'] = _jq
                    _jq.append(_fjob)
                    print(f'[Pipeline] Flow job {_fid} queued')

            job.message = f'Flow extension: generating {total} images...'
            job.progress = 45
            db.session.commit()

            _timeout = max(total * 600, 600)
            _start = time.time()
            _done = False
            while time.time() - _start < _timeout:
                time.sleep(5)
                with _lock:
                    _completed = _state.get('completed_jobs') or {}
                    _cj = _completed.get(_fid) if isinstance(_completed, dict) else None
                    if _cj and isinstance(_cj, dict) and _cj.get('state') in ('complete', 'error'):
                        _done = True
                        print(f'[Pipeline] Flow done: {_cj.get("message", "")}')
                        break
                    _profiles2 = dict(_state.get('profiles') or {})
                    for pid, info in _profiles2.items():
                        _cur = info.get('current_job')
                        if isinstance(_cur, dict) and _cur.get('job_id') == _fid:
                            _msg = _cur.get('message', '')
                            if _msg:
                                job.message = f'Flow: {_msg}'

                                # Calculate real-time progress from Flow bot status
                                import re
                                _pm = re.search(r'Prompt\s+(\d+)/(\d+)', _msg)
                                _dm = re.search(r'Download\s+(\d+)/(\d+)', _msg)
                                if _msg.startswith('Downloading') or _msg.startswith('Download'):
                                    if _dm:
                                        _di, _dt = int(_dm.group(1)), int(_dm.group(2))
                                        job.progress = 80 + int((_di / max(_dt, 1)) * 15)
                                    else:
                                        job.progress = 80
                                elif _pm:
                                    _pi, _pt = int(_pm.group(1)), int(_pm.group(2))
                                    job.progress = 45 + int((_pi / max(_pt, 1)) * 35)
                                elif 'complete' in _msg.lower():
                                    job.progress = 95

                                try: db.session.commit()
                                except Exception: pass
                if not _check_job_control(job, db):
                    return

            time.sleep(3)
            _after = set(os.listdir(_dl_dir)) if os.path.exists(_dl_dir) else set()
            _new = sorted([f for f in (_after - _before) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
            print(f'[Pipeline] {len(_new)} files downloaded')

            import shutil
            for i, fname in enumerate(_new[:total]):
                src = os.path.join(_dl_dir, fname)
                dst = os.path.join(output_dir, fname)
                try: shutil.move(src, dst)
                except: shutil.copy2(src, dst)
                rel_path = os.path.relpath(dst,
                    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
                ).replace('\\', '/')
                plan_item = content_plan[i] if content_plan and i < len(content_plan) else {}
                ptxt = _prompt_texts[i] if i < len(_prompt_texts) else ''
                gen = Generation(
                    user_id=job.user_id, collection_id=collection.id,
                    output_path=rel_path, pomelli_feature='agent',
                    status='completed', tags=(str(plan_item.get('title', '')) + ' | ' + ptxt[:100]),
                )
                db.session.add(gen)
                db.session.commit()
                results.append({'id': i+1, 'filename': fname, 'path': rel_path, 'engine': 'flow-ext', 'type': str(plan_item.get('type', 'a_plus'))})

            print(f'[Pipeline] {len(results)} images saved to collection')

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