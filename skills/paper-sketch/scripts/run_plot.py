"""기존 Diagram 경로와 분리된 원본 PaperBanana Plot 실행 경계."""
import json

from bridge import FileBridge, install_bridge, write_json
from execution import begin_execution, retrieval_started, finish_execution
from state import save_result, save_failed_result, summarize_result


async def run_plot(args):
    """참고 검색·설계·스타일·코드 실행·검토 및 결과 저장."""
    if args.action != 'generate':
        raise ValueError('Plot supports generate/inspect/select; PBInteract refinement is not connected')
    output = args.output.resolve()
    bridge = FileBridge(output / 'requests', timeout=args.timeout, independent_text=True)
    install_bridge(bridge)
    from plot_runtime import make_plot_processor, final_plot_review
    processor = make_plot_processor(args, bridge)
    source = json.loads(args.input.read_text(encoding='utf-8'))
    data = {'task_name': 'plot', 'content': source['content'], 'visual_intent': source['visual_intent'],
            'additional_info': source.get('additional_info', {}), 'max_critic_rounds': args.critic_rounds,
            'chat_history': [{'role': 'assistant', 'content': 'Plot generated.'}]}
    # 원본 Plot은 figsize·tight bbox로 크기를 결정하며 Diagram의 21:9 기본값은 미적용
    if 'rounded_ratio' in data['additional_info']:
        data['requested_image_ratio'] = data['additional_info']['rounded_ratio']
    begin_execution(args, data)
    write_json(output / 'run_config.json', {'format_version': 2,
        'requested_options': data['execution_record']['requested_options'], 'execution_policy': {
            'task': 'plot', 'text_host': 'independent-codex', 'expected_image_tool': 'matplotlib-local',
            'dpi': 300, 'plot_timeout_seconds': args.plot_timeout, 'final_review': 'read_only',
            'review_response_attempts': 2, 'pbinteract': 'unsupported'}})
    try:
        retrieval_started(data)
        await processor.retriever_agent.process(data, args.retrieval)
        data = await processor.process_single_query(data, do_eval=False)
        if not data.get(data['eval_image_field']):
            valid = [key for key, value in data.items() if key.endswith('_base64_jpg') and value]
            if not valid:
                raise RuntimeError('Plot generation failed: no valid image; inspect plot_execution.json')
            data['eval_image_field'] = valid[-1]
            data['selection_fallback_reason'] = 'Selected plot unavailable; retained last valid image'
        data['final_review'] = await final_plot_review(processor, data)
    except Exception as error:
        data['plot_execution_history'] = processor.visualizer_agent.calls
        data['review_validation_history'] = bridge.review_calls
        finish_execution(data, bridge.request_paths, 'failed')
        await save_failed_result(output, data, error)
        raise
    finally:
        processor.visualizer_agent.process_executor.shutdown(wait=True)
    data['plot_execution_history'] = processor.visualizer_agent.calls
    data['review_validation_history'] = bridge.review_calls
    failed = sum(call['status'] != 'succeeded' for call in data['plot_execution_history'])
    status = 'completed_with_plot_failures' if failed else 'complete'
    if data['final_review']['status'] == 'review_failed':
        status = 'completed_with_review_failure'
    elif data['final_review']['status'] == 'issues_remaining' and status == 'complete':
        status = 'completed_with_issues'
    data['plot_generation_status'] = status
    finish_execution(data, bridge.request_paths, status)
    await save_result(output, data, action='generate')
    print(json.dumps({'status': status, 'plot_failures': failed, 'result': str(output / 'result.json'),
                      'image': str(output / 'final.jpg'), 'code': str(output / 'final.py'),
                      'final_review': summarize_result(data)['final_review']}))
