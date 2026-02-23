const { PrismaClient } = require('@prisma/client');
const fs = require('fs');
const csv = require('csv-parser');
const path = require('path');

const prisma = new PrismaClient();

async function readCSV(filePath) {
  return new Promise((resolve, reject) => {
    const results = [];
    fs.createReadStream(filePath)
      .pipe(csv())
      .on('data', (data) => results.push(data))
      .on('end', () => resolve(results))
      .on('error', (error) => reject(error));
  });
}

function parseValue(value) {
  if (value === '' || value === null || value === undefined) {
    return null;
  }
  return value;
}

function parseIntValue(value) {
  if (value === '' || value === null || value === undefined) {
    return null;
  }
  const parsed = parseInt(value, 10);
  return isNaN(parsed) ? null : parsed;
}

function parseDecimalValue(value) {
  if (value === '' || value === null || value === undefined) {
    return null;
  }
  const parsed = parseFloat(value);
  return isNaN(parsed) ? null : parsed;
}

async function loadCourses() {
  console.log('Loading courses...');
  const dataPath = path.join(__dirname, '../data/courses.csv');
  const data = await readCSV(dataPath);
  
  let count = 0;
  for (const row of data) {
    await prisma.course.upsert({
      where: {
        codeModule_codePresentation: {
          codeModule: row.code_module,
          codePresentation: row.code_presentation,
        },
      },
      update: {},
      create: {
        codeModule: row.code_module,
        codePresentation: row.code_presentation,
        modulePresentationLength: parseIntValue(row.module_presentation_length),
      },
    });
    count++;
    if (count % 10 === 0) {
      console.log(`  Loaded ${count} courses...`);
    }
  }
  console.log(`✓ Loaded ${count} courses`);
}

async function loadStudentInfo() {
  console.log('Loading student info...');
  const dataPath = path.join(__dirname, '../data/studentInfo.csv');
  const data = await readCSV(dataPath);
  
  let count = 0;
  const batchSize = 500;
  
  for (let i = 0; i < data.length; i += batchSize) {
    const batch = data.slice(i, i + batchSize);
    
    await prisma.$transaction(
      batch.map((row) =>
        prisma.studentInfo.upsert({
          where: {
            codeModule_codePresentation_idStudent: {
              codeModule: row.code_module,
              codePresentation: row.code_presentation,
              idStudent: parseInt(row.id_student, 10),
            },
          },
          update: {},
          create: {
            codeModule: row.code_module,
            codePresentation: row.code_presentation,
            idStudent: parseInt(row.id_student, 10),
            gender: parseValue(row.gender),
            region: parseValue(row.region),
            highestEducation: parseValue(row.highest_education),
            imdBand: parseValue(row.imd_band),
            ageBand: parseValue(row.age_band),
            numOfPrevAttempts: parseIntValue(row.num_of_prev_attempts),
            studiedCredits: parseIntValue(row.studied_credits),
            disability: parseValue(row.disability),
            finalResult: parseValue(row.final_result),
          },
        })
      )
    );
    
    count += batch.length;
    console.log(`  Loaded ${count} student info records...`);
  }
  console.log(`✓ Loaded ${count} student info records`);
}

async function loadStudentRegistration() {
  console.log('Loading student registrations...');
  const dataPath = path.join(__dirname, '../data/studentRegistration.csv');
  const data = await readCSV(dataPath);
  
  let count = 0;
  const batchSize = 500;
  
  for (let i = 0; i < data.length; i += batchSize) {
    const batch = data.slice(i, i + batchSize);
    
    await prisma.$transaction(
      batch.map((row) =>
        prisma.studentRegistration.upsert({
          where: {
            codeModule_codePresentation_idStudent: {
              codeModule: row.code_module,
              codePresentation: row.code_presentation,
              idStudent: parseInt(row.id_student, 10),
            },
          },
          update: {},
          create: {
            codeModule: row.code_module,
            codePresentation: row.code_presentation,
            idStudent: parseInt(row.id_student, 10),
            dateRegistration: parseIntValue(row.date_registration),
            dateUnregistration: parseIntValue(row.date_unregistration),
          },
        })
      )
    );
    
    count += batch.length;
    console.log(`  Loaded ${count} student registrations...`);
  }
  console.log(`✓ Loaded ${count} student registrations`);
}

async function loadAssessments() {
  console.log('Loading assessments...');
  const dataPath = path.join(__dirname, '../data/assessments.csv');
  const data = await readCSV(dataPath);
  
  let count = 0;
  for (const row of data) {
    await prisma.assessment.upsert({
      where: {
        idAssessment: parseInt(row.id_assessment, 10),
      },
      update: {},
      create: {
        codeModule: row.code_module,
        codePresentation: row.code_presentation,
        idAssessment: parseInt(row.id_assessment, 10),
        assessmentType: parseValue(row.assessment_type),
        date: parseIntValue(row.date),
        weight: parseDecimalValue(row.weight),
      },
    });
    count++;
    if (count % 50 === 0) {
      console.log(`  Loaded ${count} assessments...`);
    }
  }
  console.log(`✓ Loaded ${count} assessments`);
}

async function loadStudentAssessment() {
  console.log('Loading student assessments...');
  const dataPath = path.join(__dirname, '../data/studentAssessment.csv');
  const data = await readCSV(dataPath);
  
  let count = 0;
  const batchSize = 1000;
  
  for (let i = 0; i < data.length; i += batchSize) {
    const batch = data.slice(i, i + batchSize);
    
    await prisma.$transaction(
      batch.map((row) =>
        prisma.studentAssessment.upsert({
          where: {
            idAssessment_idStudent: {
              idAssessment: parseInt(row.id_assessment, 10),
              idStudent: parseInt(row.id_student, 10),
            },
          },
          update: {},
          create: {
            idAssessment: parseInt(row.id_assessment, 10),
            idStudent: parseInt(row.id_student, 10),
            dateSubmitted: parseIntValue(row.date_submitted),
            isBanked: parseIntValue(row.is_banked),
            score: parseDecimalValue(row.score),
          },
        })
      )
    );
    
    count += batch.length;
    console.log(`  Loaded ${count} student assessments...`);
  }
  console.log(`✓ Loaded ${count} student assessments`);
}

async function loadVle() {
  console.log('Loading VLE...');
  const dataPath = path.join(__dirname, '../data/vle.csv');
  const data = await readCSV(dataPath);
  
  let count = 0;
  const batchSize = 500;
  
  for (let i = 0; i < data.length; i += batchSize) {
    const batch = data.slice(i, i + batchSize);
    
    await prisma.$transaction(
      batch.map((row) =>
        prisma.vle.upsert({
          where: {
            idSite: parseInt(row.id_site, 10),
          },
          update: {},
          create: {
            idSite: parseInt(row.id_site, 10),
            codeModule: row.code_module,
            codePresentation: row.code_presentation,
            activityType: parseValue(row.activity_type),
            weekFrom: parseIntValue(row.week_from),
            weekTo: parseIntValue(row.week_to),
          },
        })
      )
    );
    
    count += batch.length;
    console.log(`  Loaded ${count} VLE records...`);
  }
  console.log(`✓ Loaded ${count} VLE records`);
}

async function loadStudentVle() {
  console.log('Loading student VLE interactions...');
  const dataPath = path.join(__dirname, '../data/studentVle.csv');
  const data = await readCSV(dataPath);
  
  console.log(`Total student VLE records in CSV: ${data.length}`);
  console.log('Processing with chunk-based aggregation...');
  
  let count = 0;
  const chunkSize = 50000; // Process 50k records at a time
  const batchSize = 1000;  // Insert 1k at a time
  
  for (let chunkStart = 0; chunkStart < data.length; chunkStart += chunkSize) {
    const chunk = data.slice(chunkStart, chunkStart + chunkSize);
    
    // Aggregate within this chunk
    const aggregatedMap = new Map();
    
    for (const row of chunk) {
      const date = parseIntValue(row.date);
      if (date === null) continue;
      
      const key = `${row.code_module}|${row.code_presentation}|${row.id_student}|${row.id_site}|${date}`;
      
      if (aggregatedMap.has(key)) {
        const existing = aggregatedMap.get(key);
        existing.sumClick += parseIntValue(row.sum_click) || 0;
      } else {
        aggregatedMap.set(key, {
          codeModule: row.code_module,
          codePresentation: row.code_presentation,
          idStudent: parseInt(row.id_student, 10),
          idSite: parseInt(row.id_site, 10),
          date: date,
          sumClick: parseIntValue(row.sum_click) || 0,
        });
      }
    }
    
    const aggregatedData = Array.from(aggregatedMap.values());
    
    // Insert aggregated chunk in batches
    for (let i = 0; i < aggregatedData.length; i += batchSize) {
      const batch = aggregatedData.slice(i, i + batchSize);
      
      await prisma.$transaction(
        batch.map((record) =>
          prisma.studentVle.upsert({
            where: {
              codeModule_codePresentation_idStudent_idSite_date: {
                codeModule: record.codeModule,
                codePresentation: record.codePresentation,
                idStudent: record.idStudent,
                idSite: record.idSite,
                date: record.date,
              },
            },
            update: {
              sumClick: { increment: record.sumClick },
            },
            create: record,
          })
        )
      );
      
      count += batch.length;
      if (count % 10000 === 0) {
        console.log(`  Processed ${count} unique student VLE interactions...`);
      }
    }
    
    // Clear map to free memory
    aggregatedMap.clear();
  }
  
  console.log(`✓ Loaded ${count} student VLE interactions`);
}

async function main() {
  try {
    console.log('Starting ETL process...\n');
    
    await loadCourses();
    await loadStudentInfo();
    await loadStudentRegistration();
    await loadAssessments();
    await loadStudentAssessment();
    await loadVle();
    await loadStudentVle();
    
    console.log('\n✓ ETL process completed successfully!');
  } catch (error) {
    console.error('Error during ETL process:', error);
    throw error;
  } finally {
    await prisma.$disconnect();
  }
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  });
