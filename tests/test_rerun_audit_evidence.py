import csv
import json

from punishment_sim.stage_b_validation import consistency_checks


def csv_file(path,rows,fields):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)


def test_absent_audits_are_not_reported_as_pass(tmp_path):
    csv_file(tmp_path/'false_positive_vectors.csv',[],['natural_fork_rate','conditional_loss','actor','fpr'])
    csv_file(tmp_path/'mining_configurations.csv',[],['configuration_id'])
    rows={r['check']:r for r in consistency_checks(tmp_path,[],[],[])}
    for name in ('lambda_zero_false_positive','actor_revenue_shares_sum_to_one','coalition_reward_accounting','duplicate_cache_keys'):
        assert rows[name]['status']=='NOT_CHECKED'


def test_audit_counts_come_from_current_outputs_and_zero_violation_fails(tmp_path):
    csv_file(tmp_path/'false_positive_vectors.csv',[{'natural_fork_rate':0,'conditional_loss':.01,'actor':'c1','fpr':0}],['natural_fork_rate','conditional_loss','actor','fpr'])
    csv_file(tmp_path/'mining_configurations.csv',[],['configuration_id'])
    csv_file(tmp_path/'cache_audit.csv',[{'unique_mining_simulations':12,'mining_simulations_represented':12}],['unique_mining_simulations','mining_simulations_represented'])
    (tmp_path/'checkpoint_accounting_audit.json').write_text(json.dumps({'bad_revenue_sum_vectors':0,'bad_accepted_count_payoffs':0,'bad_actor_identity_vectors':0}))
    rows={r['check']:r for r in consistency_checks(tmp_path,[],[],[])}
    assert rows['lambda_zero_false_positive']['status']=='FAIL'
    assert rows['duplicate_cache_keys']['status']=='PASS'
    assert '12' in rows['duplicate_cache_keys']['evidence'] and '451440' not in rows['duplicate_cache_keys']['evidence']
    assert rows['actor_revenue_shares_sum_to_one']['status']=='PASS'
