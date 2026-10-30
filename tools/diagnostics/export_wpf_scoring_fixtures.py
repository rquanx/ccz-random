"""Export reference results from the existing 2.2 evaluator (development only)."""
import copy
import json
from pathlib import Path

from ccz_randomizer.jobs import JOB_MAP
from ccz_randomizer.rules.config import default_rule_config, active_profile, evaluate_skill_rules, skill_types_match, evaluate_job_rules, DEFAULT_MEMBER_AFFINITY
from ccz_randomizer.rules.skill_scores import migrate_skill_scores, DEFAULT_TYPES, resolve_setting


def main():
    root = Path(__file__).resolve().parents[2]
    people = json.loads((root / 'tests/fixtures/personnel_22/randomized-personnel.json').read_text(encoding='utf-8'))[:2]
    members = [dict(name=p['name'], jobName=JOB_MAP[p['jobId']][0], jobType=JOB_MAP[p['jobId']][2],
                    skills=p['personalTalents'] + p['jobTalents']) for p in people]
    cases = []
    for migration in (False, True):
        for matching in (False, True):
            for mode in ('count', 'average', 'total'):
                for threshold in (0, 2, 4, 100):
                    config = default_rule_config()
                    profile = active_profile(config)
                    profile['threePerson']['qualifiedMembers'] = [p['name'] for p in people]
                    profile['skillQualification'] = dict(mode=mode, threshold=threshold, requiredCount=2)
                    seven = profile['sevenPerson']
                    seven['skillTypeMatchingEnabled'] = matching
                    seven['individualSkillScores'] = not migration
                    seven['skillBaseScores'] = {name: 2 for m in members for name in m['skills']}
                    # A real parameter alias must carry across custom score/type settings.
                    seven['skillBaseScores']['攻击追加-诱惑'] = 3
                    seven['skillBaseScores'].pop('攻击追加 诱惑', None)
                    seven['skillTypeOverrides'] = {'攻击追加-诱惑': 'WARRIOR'}
                    original = copy.deepcopy(config)
                    migrate_skill_scores(profile)
                    skills = {m['name']: m['skills'] for m in members}
                    effective = {m['name']: [name for name in m['skills'] if not matching or skill_types_match(m['jobType'],
                        resolve_setting(seven['skillTypeOverrides'], name, DEFAULT_TYPES.get(name, 'ALL_ROUNDER')))] for m in members}
                    result = evaluate_skill_rules(config, 20, skills, set(), set(), set(),
                                                  qualification=profile['skillQualification'], effective_skills_by_member=effective)
                    cases.append(dict(config=original, members=members, expected=dict(qualified=result.qualified,
                        total=result.metrics['skillScore'], average=result.metrics['qualificationAverage'],
                        memberScores=result.metrics['memberSkillScores'], details=result.metrics['skillDetails'])))
    target = root / 'tests/fixtures/scoring_22/skill-parity.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding='utf-8')
    export_jobs(root)


def export_jobs(root):
    people = json.loads((root / 'tests/fixtures/personnel_22/randomized-fixed-personnel.json').read_text(encoding='utf-8'))[:3]
    people += json.loads((root / 'tests/fixtures/personnel_22/randomized-personnel.json').read_text(encoding='utf-8'))[:2]
    jobs = [dict(name=JOB_MAP[p['jobId']][0], score=JOB_MAP[p['jobId']][1], type=JOB_MAP[p['jobId']][2]) for p in people]
    members = [dict(name=p['name'], **DEFAULT_MEMBER_AFFINITY[p['name']]) for p in people]
    cases = []
    for mode in ('count', 'average', 'total', 'all'):
        for threshold in (0, 7, 8, 40):
            for custom in (False, True):
                for selected in ([p['name'] for p in people], ['张宝']):
                    config = default_rule_config()
                    profile = active_profile(config)
                    profile['threePerson'].update(jobQualificationMode=mode, minJobAverage=threshold,
                                                  minQualifiedCount=min(2, len(selected)), qualifiedMembers=selected)
                    if custom:
                        profile['jobScoring'].update(baseScoreWeight=0.8, primaryBonusRate=0.2, secondaryBonusRate=0.1,
                            jobBaseScores={jobs[0]['name']: 9}, jobTypeOverrides={jobs[0]['name']: 'ALL_ROUNDER'})
                        profile['memberAffinity']['张宝'] = dict(primaryType='MASTER', secondaryType='WARRIOR')
                    result = evaluate_job_rules(config, 'three', jobs, members)
                    small_profile = {k:profile[k] for k in ('jobScoring','threePerson','memberAffinity')}
                    small_profile['memberAffinity'] = {m['name']:profile['memberAffinity'][m['name']] for m in members}
                    cases.append(dict(config=dict(activeProfile='test', profiles=dict(test=small_profile)),
                        members=members, jobs=jobs, expected=dict(qualified=result.qualified, **result.metrics)))
    (root / 'tests/fixtures/scoring_22/job-parity.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
