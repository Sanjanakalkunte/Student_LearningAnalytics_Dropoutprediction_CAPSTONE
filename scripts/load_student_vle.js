require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });
const { Pool } = require('pg');
const fs = require('fs');
const csv = require('csv-parser');
const path = require('path');
const { pipeline } = require('stream/promises');
const { Transform } = require('stream');

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

async function loadStudentVle() {
    console.log('Loading student VLE interactions via raw SQL...');
    const dataPath = path.join(__dirname, '../data/studentVle.csv');
    const client = await pool.connect();

    let count = 0;
    let totalRows = 0;
    const chunkSize = 10000;
    let buffer = [];

    async function flushBuffer() {
        if (buffer.length === 0) return;

        // Aggregate duplicates within this batch
        const aggregated = new Map();
        for (const row of buffer) {
            const key = `${row.code_module}|${row.code_presentation}|${row.id_student}|${row.id_site}|${row.date}`;
            if (aggregated.has(key)) {
                aggregated.get(key).sumClick += parseInt(row.sum_click) || 0;
            } else {
                aggregated.set(key, {
                    codeModule: row.code_module,
                    codePresentation: row.code_presentation,
                    idStudent: parseInt(row.id_student),
                    idSite: parseInt(row.id_site),
                    date: parseInt(row.date),
                    sumClick: parseInt(row.sum_click) || 0,
                });
            }
        }

        const rows = Array.from(aggregated.values());
        aggregated.clear();

        const values = [];
        const params = [];
        let paramIdx = 1;

        for (const r of rows) {
            values.push(`($${paramIdx}, $${paramIdx + 1}, $${paramIdx + 2}, $${paramIdx + 3}, $${paramIdx + 4}, $${paramIdx + 5})`);
            params.push(r.codeModule, r.codePresentation, r.idStudent, r.idSite, r.date, r.sumClick);
            paramIdx += 6;
        }

        const query = `
      INSERT INTO "studentVle" ("codeModule", "codePresentation", "idStudent", "idSite", "date", "sumClick")
      VALUES ${values.join(', ')}
      ON CONFLICT ("codeModule", "codePresentation", "idStudent", "idSite", "date")
      DO UPDATE SET "sumClick" = EXCLUDED."sumClick"
    `;

        await client.query(query, params);
        count += rows.length;
        buffer = [];

        if (count % 50000 === 0) {
            console.log(`  Inserted ${count} rows (${totalRows} CSV rows read)...`);
        }
    }

    try {
        await client.query('BEGIN');

        const stream = fs.createReadStream(dataPath).pipe(csv());

        for await (const row of stream) {
            if (row.date === '' || row.date === null || row.date === undefined) continue;
            buffer.push(row);
            totalRows++;

            if (buffer.length >= chunkSize) {
                await flushBuffer();
            }
        }

        // Flush remaining
        await flushBuffer();
        await client.query('COMMIT');

        console.log(`✓ Loaded ${count} student VLE rows (from ${totalRows} CSV rows)`);
    } catch (err) {
        await client.query('ROLLBACK');
        throw err;
    } finally {
        client.release();
        await pool.end();
    }
}

loadStudentVle()
    .then(() => {
        console.log('Done!');
        process.exit(0);
    })
    .catch((err) => {
        console.error('Error:', err);
        process.exit(1);
    });
