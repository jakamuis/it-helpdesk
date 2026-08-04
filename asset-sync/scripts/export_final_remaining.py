import os
import pandas as pd
import pymysql
from loguru import logger

def main():
    excel_path = "/app/docs/Samator Registration Asset 1.0.xlsx"
    if not os.path.exists(excel_path):
        logger.error(f"Excel file not found at {excel_path}")
        return

    logger.info("Reading full Excel file...")
    df = pd.read_excel(excel_path, engine='openpyxl')
    
    logger.info("Fetching GLPI inventory...")
    try:
        conn = pymysql.connect(host='glpi_db', user='glpi', password='glpi_password', database='glpidb')
        with conn.cursor() as cursor:
            # We fetch name (Hostname), serial, and otherserial (AM codes)
            cursor.execute("SELECT id, name, serial, otherserial FROM glpi_computers;")
            rows = cursor.fetchall()
        
        glpi_names = {str(r[1]).strip().lower() for r in rows if r[1]}
        glpi_serials = {str(r[2]).strip().lower() for r in rows if r[2]}
        glpi_otherserials = {str(r[3]).strip().lower() for r in rows if r[3]}
        conn.close()
    except Exception as e:
        logger.error(f"Failed to fetch from DB: {e}")
        return

    unmatched_indices = []

    for idx, row in df.iterrows():
        is_synced = False
        
        # 1. Check AM- codes
        for col in df.columns:
            val = str(row.get(col)).strip()
            if val.lower().startswith('am-'):
                if val.lower() in glpi_otherserials:
                    is_synced = True
                break
                
        if is_synced:
            continue
            
        # 2. Check Hostname or Serial
        hostname = str(row.get("Hostname", "")).strip().lower()
        if hostname and hostname != 'nan' and hostname in glpi_names:
            is_synced = True
            continue
            
        serial = str(row.get("Serial Number", "")).strip().lower()
        if serial and serial != 'nan' and serial in glpi_serials:
            is_synced = True
            continue

        unmatched_indices.append(idx)

    # Export unmatched
    df_unmatched = df.loc[unmatched_indices]
    out_path = "/app/docs/Samator Registration Asset 1.0_Final_Remaining.xlsx"
    df_unmatched.to_excel(out_path, index=False)
    
    logger.info(f"Total rows in Excel: {len(df)}")
    logger.info(f"Total synced rows filtered out: {len(df) - len(unmatched_indices)}")
    logger.info(f"Total remaining unsynced rows exported: {len(df_unmatched)}")

if __name__ == "__main__":
    main()
