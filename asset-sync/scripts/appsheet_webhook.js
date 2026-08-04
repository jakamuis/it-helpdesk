/**
 * Google Apps Script Webhook Example for AppSheet
 * This script sends row changes to the asset-sync service.
 */

const SYNC_URL = "http://your-server-ip:8000/api/v1/sync";
const API_KEY = "your_secure_api_key_here";

function onEdit(e) {
  // If not triggered by AppSheet, exit.
  // In reality, this might be triggered directly from AppSheet's Webhook workflow.
}

// AppSheet Webhook Function
// Use this inside AppSheet -> Automation -> Tasks -> Call a Webhook
function triggerWebhook(record) {
  const payload = {
    "qrcode": record.QRCODE_UNIT,
    "name": record.Asset_Name,
    "brand": record.Brand,
    "model": record.Model,
    "category": record.Category,
    "hostname": record.Hostname,
    "serial": record.Serial_Number,
    "department": record.Department,
    "location": record.Location,
    "user": record.Assigned_User,
    "purchase_date": record.Purchase_Date,
    "warranty": record.Warranty,
    "status": record.Status
  };

  const options = {
    'method': 'post',
    'contentType': 'application/json',
    'headers': {
      'X-API-KEY': API_KEY
    },
    'payload': JSON.stringify(payload),
    'muteHttpExceptions': true
  };

  try {
    const response = UrlFetchApp.fetch(SYNC_URL, options);
    Logger.log("Response: " + response.getContentText());
  } catch (err) {
    Logger.log("Error: " + err);
  }
}
