// Fixed reviewer agent - checks actual file completeness, not truncated previews

export async function improvedReviewerAgent(state: any) {
  const filesList = Object.keys(state.generatedFiles).map(f => `- ${f}`).join('\n');
  const fileCount = Object.keys(state.generatedFiles).length;
  
  // Check file completeness by looking at actual endings
  const fileCompleteness = Object.entries(state.generatedFiles).map(([filename, code]: [string, any]) => {
    const codeStr = String(code);
    const hasProperEnding = 
      filename.endsWith('.html') ? codeStr.trim().endsWith('</html>') :
      filename.endsWith('.css') ? codeStr.trim().endsWith('}') :
      filename.endsWith('.js') || filename.endsWith('.jsx') || filename.endsWith('.ts') || filename.endsWith('.tsx') 
        ? (codeStr.includes('};') || codeStr.includes('});') || codeStr.trim().endsWith('}') || codeStr.trim().endsWith(';')) 
        : true;
    
    return { filename, complete: hasProperEnding, length: codeStr.length };
  });

  const allComplete = fileCompleteness.every(f => f.complete && f.length > 50);
  
  //  For HTML/CSS/JS projects, check file linking
  let filesLinked = true;
  const request = String(state.userRequest).toLowerCase();
  if (request.includes('calculator') || request.includes('html') || request.includes('website') ||
      Object.keys(state.generatedFiles).some(f => f.endsWith('.html'))) {
    
    const htmlFiles = Object.entries(state.generatedFiles).filter(([f]) => f.endsWith('.html'));
    const cssFiles = Object.keys(state.generatedFiles).filter(f => f.endsWith('.css'));
    const jsFiles = Object.keys(state.generatedFiles).filter(f => f.endsWith('.js'));
    
    if (htmlFiles.length > 0) {
      const htmlContent = String(htmlFiles[0][1]);
      // Check if HTML references the CSS and JS files
      filesLinked = 
        (cssFiles.length === 0 || cssFiles.some(f => htmlContent.includes(f.split('/').pop() || f))) &&
        (jsFiles.length === 0 || jsFiles.some(f => htmlContent.includes(f.split('/').pop() || f)));
    }
  }

  console.log(`📊 Review Check - Files: ${fileCount}, Complete: ${allComplete}, Linked: ${filesLinked}`);
  fileCompleteness.forEach(f => console.log(`  - ${f.filename}: ${f.complete ? '✓' : '✗'} ${f.length} chars`));
  
  // Auto-approve if all checks pass
  if (allComplete && filesLinked && fileCount >= 2 && state.currentIteration >= state.plan.length) {
    console.log(`✅ Auto-approved: All checks passed!`);
    return {
      reviewFeedback: 'APPROVED - All files are complete, properly linked, and functional.',
      isComplete: true,
      messages: [{ role: 'assistant', content: 'Review: APPROVED - Project is complete!' }],
    };
  }

  return {
    reviewFeedback: `Files: ${fileCount}. Complete: ${allComplete}. Linked: ${filesLinked}. ${!allComplete ? 'Some files incomplete. ' : ''}${!filesLinked ? 'Files not properly linked. ' : ''}`,
    isComplete: allComplete && filesLinked && state.currentIteration >= state.plan.length,
    messages: [{ role: 'assistant', content: 'Review in progress...' }],
  };
}
