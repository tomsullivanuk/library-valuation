"""Saved storage-visit work, separate from copy reservations and handovers."""
from datetime import date


def save_entry(state, request, tasks, stamp, pick_lookup):
    visit = request.get('visit_date')
    if not isinstance(visit, str) or date.fromisoformat(visit).isoformat() != visit:
        raise ValueError('Choose a valid visit date')
    note, done = request.get('note', ''), request.get('done')
    if not isinstance(note, str) or len(note) > 4000 or type(done) is not bool:
        raise ValueError('Invalid visit note or checkbox')
    source = request.get('source')
    if source == 'action':
        task = tasks.get(request.get('id'))
        if not task or task['fingerprint'] != request.get('fingerprint'):
            raise ValueError('This question changed. Reload before saving your answer.')
        key = 'action:' + task['id']
        identity = dict(source=source, id=task['id'], fingerprint=task['fingerprint'])
    elif source == 'pick':
        identity = pick_lookup(request)
        key = 'pick:' + identity['submission'] + ':' + identity['reference'] + ':' + identity['slot']
        identity = dict(identity, source=source)
    else:
        raise ValueError('Unknown visit item')
    entries = state.setdefault('storage_visits', {}).setdefault(visit, {})
    previous = entries.get(key, {})
    # Retain enough context to show completed checks during this visit after reload.
    value = dict(identity, title=task['title'] if source == 'action' else identity['title'],
                 done=done, note=note, updated_at=stamp)
    if source == 'action':
        saved = state['actions'].get(task['id'], {})
        same_question = saved.get('fingerprint') == task['fingerprint']
        status = saved.get('status', 'open') if same_question else 'open'
        # A saved answer updates Action Items; marking complete or reopening is explicit.
        if done or previous.get('done'):
            status = 'complete' if done else 'open'
        action = dict(saved if same_question else {})
        action.update(status=status, note=note, fingerprint=task['fingerprint'], updated_at=stamp,
                      deferred_until=action.get('deferred_until', '') if status == 'deferred' else '')
        state['actions'][task['id']] = action
    entries[key] = value
    return dict(kind='storage_visit', visit_date=visit, key=key, **value)
