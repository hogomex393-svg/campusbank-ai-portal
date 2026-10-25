"""Export aggregate answer-feedback counts. No account names, comments or chats."""
import argparse,json,sqlite3
from pathlib import Path
def main():
    p=argparse.ArgumentParser();p.add_argument('--db',required=True,type=Path);p.add_argument('--output',required=True,type=Path);args=p.parse_args()
    if not args.db.is_file():p.error('The database does not exist.')
    with sqlite3.connect('file:'+args.db.resolve().as_posix()+'?mode=ro',uri=True) as db:
        rows=db.execute('SELECT helpful,reason,COUNT(*) FROM answer_feedback GROUP BY helpful,reason').fetchall()
    result={'total':sum(r[2] for r in rows),'groups':[{'helpful':bool(h),'reason':reason,'count':count} for h,reason,count in rows],'note':'Aggregate user feedback only; it is not a controlled accuracy evaluation.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
