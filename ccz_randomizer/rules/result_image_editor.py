"""Rule-scoped selection of people shown in result images."""
from ccz_randomizer.ui.member_picker import show_member_picker


def show_result_image_members(parent, settings, scoring_members, on_confirm):
    member_names = tuple(scoring_members)
    def confirm(mode, chosen):
        on_confirm({'mode': mode, 'members': chosen if mode == 'custom' else settings.get('members', [])})
    return show_member_picker(parent, member_names, settings.get('members') or member_names, confirm,
        cache_key='result-image', title='结果图人物',
        description='只控制结果图展示，不改变兵种、特技评分和合格判断。',
        follow_mode=settings.get('mode', 'selected'), empty_message='请至少选择一名结果图展示人物。')
